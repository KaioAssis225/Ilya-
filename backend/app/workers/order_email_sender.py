"""Worker persistente para enviar PDFs finalizados pelo Resend."""

from __future__ import annotations

import asyncio
import base64
import html
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.order_documents import read_order_pdf
from app.db.session import AsyncSessionLocal
from app.models.order import Order
from app.models.order_email import OrderDocument, OrderEmailDelivery
from app.services.resend_webhook import reconcile_delivery_events


logger = logging.getLogger("ilya.order_email_sender")
CLAIM_LEASE = timedelta(minutes=15)
IDLE_SLEEP_SECONDS = 5


class PermanentDeliveryError(RuntimeError):
    pass


def _safe_error(exc: Exception) -> str:
    value = str(exc).replace(settings.RESEND_API_KEY, "[REDACTED]")
    return value[:500]


async def claim_next_job(db: AsyncSession, now: datetime) -> OrderEmailDelivery | None:
    job = (
        await db.execute(
            select(OrderEmailDelivery)
            .where(
                OrderEmailDelivery.recipient_email.is_not(None),
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
            .order_by(OrderEmailDelivery.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "processing"
    job.attempts += 1
    job.next_attempt_at = now + CLAIM_LEASE
    await db.commit()
    return job


def _message(order: Order, recipient_name: str) -> tuple[str, str, str]:
    code = html.escape(order.code)
    name = html.escape(recipient_name)
    if order.market_code == "EU" and order.locale == "en-GB":
        subject = f"Order {order.code} — Ilya"
        text = f"Hello {recipient_name},\n\nThe PDF for order {order.code} is attached.\n"
        body = f"<p>Hello {name},</p><p>The PDF for order <strong>{code}</strong> is attached.</p>"
    elif order.market_code == "EU":
        subject = f"Pedido {order.code} — Ilya"
        text = f"Olá {recipient_name},\n\nSegue em anexo o PDF do pedido {order.code}.\n"
        body = f"<p>Olá {name},</p><p>Segue em anexo o PDF do pedido <strong>{code}</strong>.</p>"
    else:
        subject = f"Pedido {order.code} — Ilya"
        text = f"Olá {recipient_name},\n\nSegue em anexo o PDF do pedido {order.code}.\n"
        body = f"<p>Olá {name},</p><p>Segue em anexo o PDF do pedido <strong>{code}</strong>.</p>"
    return subject, text + "\nEquipe Ilya", body + "<p>Equipe Ilya</p>"


async def deliver_job(
    client: httpx.AsyncClient,
    db: AsyncSession,
    job: OrderEmailDelivery,
) -> str:
    order = await db.get(Order, job.order_id)
    document = await db.get(OrderDocument, job.document_id)
    if order is None or document is None:
        raise PermanentDeliveryError("Pedido ou documento não encontrado.")
    content = await read_order_pdf(document.storage_key, document.market_code)
    subject, text_body, html_body = _message(order, job.recipient_name)
    response = await client.post(
        f"{settings.RESEND_API_BASE_URL.rstrip('/')}/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Idempotency-Key": job.idempotency_key,
            "Content-Type": "application/json",
        },
        json={
            "from": f"{settings.RESEND_FROM_NAME} <{settings.RESEND_FROM_EMAIL}>",
            "to": [job.recipient_email],
            "reply_to": settings.RESEND_REPLY_TO,
            "subject": subject,
            "text": text_body,
            "html": html_body,
            "attachments": [
                {
                    "content": base64.b64encode(content).decode("ascii"),
                    "filename": document.filename,
                    "content_type": "application/pdf",
                }
            ],
            "tags": [
                {"name": "kind", "value": "order_pdf"},
                {"name": "market", "value": order.market_code.lower()},
            ],
        },
    )
    if response.status_code == 429 or response.status_code >= 500:
        raise httpx.HTTPStatusError(
            f"Resend temporariamente indisponível ({response.status_code}).",
            request=response.request,
            response=response,
        )
    if response.status_code >= 400:
        raise PermanentDeliveryError(f"Resend recusou o envio ({response.status_code}).")
    message_id = response.json().get("id")
    if not message_id:
        raise httpx.HTTPError("Resposta do Resend sem identificador da mensagem.")
    return str(message_id)


async def _record_failure(db: AsyncSession, job: OrderEmailDelivery, exc: Exception) -> None:
    await db.rollback()
    current = await db.get(OrderEmailDelivery, job.id, populate_existing=True)
    if current is None:
        return
    current.last_error = _safe_error(exc)
    current.provider_message_id = None
    if isinstance(exc, PermanentDeliveryError) or current.attempts >= settings.RESEND_MAX_ATTEMPTS:
        current.status = "failed"
        current.next_attempt_at = None
    else:
        current.status = "pending"
        current.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            seconds=min(3600, 60 * (2 ** (current.attempts - 1)))
        )
    await db.commit()


async def process_due_jobs(
    db: AsyncSession, client: httpx.AsyncClient, *, limit: int = 10
) -> int:
    processed = 0
    while processed < limit:
        job = await claim_next_job(db, datetime.now(timezone.utc))
        if job is None:
            break
        processed += 1
        try:
            job.provider_message_id = await deliver_job(client, db, job)
            job.status = "accepted"
            job.accepted_at = datetime.now(timezone.utc)
            job.next_attempt_at = None
            job.last_error = None
            await db.commit()
            await reconcile_delivery_events(db, job.id)
            await db.commit()
        except Exception as exc:
            await _record_failure(db, job, exc)
    return processed


async def run_forever() -> None:
    timeout = httpx.Timeout(settings.RESEND_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    processed = await process_due_jobs(db, client)
            except Exception:
                logger.exception("Falha ao processar a fila de e-mails de pedidos")
                processed = 0
            if processed == 0:
                await asyncio.sleep(IDLE_SLEEP_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not settings.ORDER_EMAIL_ENABLED:
        logger.info("ORDER_EMAIL_ENABLED=false; worker não inicia.")
        return
    if not settings.RESEND_API_KEY or not settings.RESEND_FROM_EMAIL:
        raise RuntimeError("Envio de pedidos exige RESEND_API_KEY e RESEND_FROM_EMAIL.")
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
