"""Worker do PDF e das entregas de e-mail dos pedidos."""
import argparse
import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.order_documents import OrderDocumentStorageError, get_document, put_document
from app.db.session import AsyncSessionLocal
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.services.order_email_events import apply_orphan_events, apply_pending_events
from app.services.order_email_jobs import recipient_is_allowed
from app.services.pdf_renderer import PdfRendererUnavailable, get_pdf_renderer
from app.services.resend_client import (
    PermanentEmailError,
    TemporaryEmailError,
    build_order_email,
    send_email,
)


logger = logging.getLogger("ilya.order_email_sender")
CLAIM_LEASE = timedelta(minutes=10)
RETRY_WINDOW = timedelta(hours=24)
MISSING_PROVIDER_WARNING_INTERVAL = timedelta(minutes=10)
_last_missing_provider_warning_at: datetime | None = None


def retry_delay(attempts: int) -> timedelta:
    exponent = min(6, max(0, attempts - 1))
    return timedelta(seconds=min(30 * (2 ** exponent), 30 * 60))


def retry_window_expired(first_attempt_at: datetime, now: datetime) -> bool:
    return now - first_attempt_at >= RETRY_WINDOW


async def claim_next_document(
    db: AsyncSession, now: datetime
) -> OrderEmailDocument | None:
    document = (
        await db.execute(
            select(OrderEmailDocument)
            .where(
                or_(
                    and_(
                        OrderEmailDocument.status == "pending",
                        or_(
                            OrderEmailDocument.next_attempt_at.is_(None),
                            OrderEmailDocument.next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        OrderEmailDocument.status == "processing",
                        OrderEmailDocument.next_attempt_at <= now,
                    ),
                )
            )
            .order_by(OrderEmailDocument.created_at, OrderEmailDocument.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if document is None:
        return None
    document.status = "processing"
    document.attempts += 1
    if document.first_attempt_at is None:
        document.first_attempt_at = now
    document.next_attempt_at = now + CLAIM_LEASE
    await db.commit()
    return document


async def claim_next_delivery(
    db: AsyncSession, now: datetime
) -> OrderEmailDelivery | None:
    delivery = (
        await db.execute(
            select(OrderEmailDelivery)
            .join(
                OrderEmailDocument,
                OrderEmailDocument.id == OrderEmailDelivery.document_id,
            )
            .where(
                OrderEmailDocument.status == "ready",
                or_(
                    and_(
                        OrderEmailDelivery.status == "pending",
                        or_(
                            OrderEmailDelivery.next_attempt_at.is_(None),
                            OrderEmailDelivery.next_attempt_at <= now,
                        ),
                    ),
                    and_(
                        OrderEmailDelivery.status == "processing",
                        OrderEmailDelivery.next_attempt_at <= now,
                    ),
                ),
            )
            .order_by(OrderEmailDelivery.created_at, OrderEmailDelivery.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if delivery is None:
        return None
    delivery.status = "processing"
    delivery.attempts += 1
    if delivery.first_attempt_at is None:
        delivery.first_attempt_at = now
    delivery.next_attempt_at = now + CLAIM_LEASE
    await db.commit()
    return delivery


async def _mark_document_failed(
    db: AsyncSession,
    document: OrderEmailDocument,
    code: str,
) -> None:
    document.status = "failed"
    document.last_error = code
    document.next_attempt_at = None
    deliveries = (
        await db.execute(
            select(OrderEmailDelivery).where(
                OrderEmailDelivery.document_id == document.id,
                OrderEmailDelivery.status.in_(("pending", "processing")),
            )
        )
    ).scalars().all()
    for delivery in deliveries:
        delivery.status = "needs_review"
        delivery.next_attempt_at = None
        delivery.last_error = code
    await db.commit()


async def _record_document_temporary(
    db: AsyncSession,
    document: OrderEmailDocument,
    code: str,
    now: datetime,
) -> None:
    first_attempt_at = document.first_attempt_at or now
    if retry_window_expired(first_attempt_at, now):
        await _mark_document_failed(db, document, code)
        return
    document.status = "pending"
    document.last_error = code
    document.next_attempt_at = now + retry_delay(document.attempts)
    await db.commit()


async def _reload_document_after_error(
    db: AsyncSession,
    document_id,
) -> OrderEmailDocument:
    await db.rollback()
    document = await db.get(
        OrderEmailDocument,
        document_id,
        populate_existing=True,
    )
    if document is None:
        raise RuntimeError("Documento de e-mail não encontrado após rollback.")
    return document


async def _process_document(
    db: AsyncSession,
    document: OrderEmailDocument,
    renderer,
) -> None:
    now = datetime.now(timezone.utc)
    document_id = document.id
    try:
        content = await renderer.render(document.snapshot)
        if not isinstance(content, bytes) or not content.startswith(b"%PDF"):
            await _mark_document_failed(db, document, "invalid_pdf")
            return
        storage_key, digest, size = await put_document(
            document.market_code,
            document.order_id,
            document.version,
            content,
        )
        document.storage_key = storage_key
        document.sha256 = digest
        document.size_bytes = size
        document.generated_at = now
        document.status = "ready"
        document.next_attempt_at = None
        document.last_error = None
        await db.commit()
    except PdfRendererUnavailable:
        document = await _reload_document_after_error(db, document_id)
        await _record_document_temporary(
            db, document, "renderer_unavailable", now
        )
    except OrderDocumentStorageError as exc:
        document = await _reload_document_after_error(db, document_id)
        await _record_document_temporary(db, document, exc.code, now)
    except Exception:
        document = await _reload_document_after_error(db, document_id)
        await _record_document_temporary(db, document, "render_failed", now)


async def _record_delivery_temporary(
    db: AsyncSession,
    delivery: OrderEmailDelivery,
    code: str,
    now: datetime,
) -> None:
    first_attempt_at = delivery.first_attempt_at or now
    if retry_window_expired(first_attempt_at, now):
        delivery.status = "needs_review"
        delivery.next_attempt_at = None
    else:
        delivery.status = "pending"
        delivery.next_attempt_at = now + retry_delay(delivery.attempts)
    delivery.last_error = code
    await db.commit()


async def _reload_delivery_after_error(
    db: AsyncSession,
    delivery_id,
) -> OrderEmailDelivery:
    await db.rollback()
    delivery = await db.get(
        OrderEmailDelivery,
        delivery_id,
        populate_existing=True,
    )
    if delivery is None:
        raise RuntimeError("Entrega de e-mail não encontrada após rollback.")
    return delivery


async def _process_delivery(
    db: AsyncSession,
    delivery: OrderEmailDelivery,
    sender,
) -> None:
    now = datetime.now(timezone.utc)
    delivery_id = delivery.id
    if settings.ORDER_EMAIL_MODE == "test" and not recipient_is_allowed(
        delivery.recipient_email
    ):
        delivery.status = "skipped"
        delivery.last_error = "not_in_allowlist"
        delivery.next_attempt_at = None
        await db.commit()
        return
    document = await db.get(OrderEmailDocument, delivery.document_id)
    try:
        if document is None or not document.storage_key:
            raise OrderDocumentStorageError("document_not_found")
        pdf = await get_document(document.market_code, document.storage_key)
        content = build_order_email(document.snapshot, pdf)
        message_id = await sender(
            idempotency_key=delivery.idempotency_key,
            to=delivery.recipient_email,
            **content,
        )
        delivery.provider_message_id = message_id
        delivery.status = "accepted"
        delivery.accepted_at = now
        delivery.next_attempt_at = None
        delivery.last_error = None
        # O evento pode ter chegado antes do commit do provider_message_id.
        await apply_orphan_events(db, delivery)
        await db.commit()
    except PermanentEmailError as exc:
        delivery = await _reload_delivery_after_error(db, delivery_id)
        delivery.status = "failed"
        delivery.last_error = exc.code
        delivery.next_attempt_at = None
        await db.commit()
    except TemporaryEmailError as exc:
        delivery = await _reload_delivery_after_error(db, delivery_id)
        await _record_delivery_temporary(db, delivery, exc.code, now)
    except OrderDocumentStorageError as exc:
        delivery = await _reload_delivery_after_error(db, delivery_id)
        await _record_delivery_temporary(db, delivery, exc.code, now)
    except Exception:
        delivery = await _reload_delivery_after_error(db, delivery_id)
        await _record_delivery_temporary(
            db, delivery, "provider_unavailable", now
        )


async def _warn_missing_provider_config(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> None:
    global _last_missing_provider_warning_at
    now = now or datetime.now(timezone.utc)
    if (
        _last_missing_provider_warning_at is not None
        and now - _last_missing_provider_warning_at
        < MISSING_PROVIDER_WARNING_INTERVAL
    ):
        return
    pending = (
        await db.execute(
            select(func.count()).select_from(OrderEmailDelivery).where(
                OrderEmailDelivery.status == "pending"
            )
        )
    ).scalar_one()
    if pending:
        logger.warning(
            "Configuração Resend incompleta; entregas pendentes=%s",
            pending,
        )
        _last_missing_provider_warning_at = now


async def process_due(
    db: AsyncSession,
    *,
    limit: int = 10,
    renderer=None,
    sender=None,
) -> int:
    """Processa documentos antes das entregas, com commit antes de cada I/O."""
    if settings.ORDER_EMAIL_MODE == "off":
        return 0
    if await apply_pending_events(db):
        await db.commit()
    renderer = renderer or get_pdf_renderer()
    sender = sender or send_email
    processed = 0
    while processed < limit:
        document = await claim_next_document(db, datetime.now(timezone.utc))
        if document is None:
            break
        processed += 1
        await _process_document(db, document, renderer)

    if not settings.RESEND_API_KEY or not settings.ORDER_EMAIL_FROM:
        await _warn_missing_provider_config(db)
        return processed

    while processed < limit:
        delivery = await claim_next_delivery(db, datetime.now(timezone.utc))
        if delivery is None:
            break
        processed += 1
        await _process_delivery(db, delivery, sender)
    return processed


async def run_once(*, limit: int = 10, renderer=None, sender=None) -> int:
    if settings.ORDER_EMAIL_MODE == "off":
        return 0
    async with AsyncSessionLocal() as db:
        return await process_due(
            db,
            limit=limit,
            renderer=renderer,
            sender=sender,
        )


async def _run_loop() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    while not stop.is_set():
        await run_once()
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.ORDER_EMAIL_POLL_SECONDS
            )
        except asyncio.TimeoutError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_once() if args.once else _run_loop())


if __name__ == "__main__":
    main()
