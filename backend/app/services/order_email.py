from __future__ import annotations

import base64
import binascii
import hashlib
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.order_documents import document_key, persist_order_pdf
from app.models.client import Client
from app.models.order import Order
from app.models.order_email import OrderDocument, OrderEmailDelivery
from app.models.representative import Representative


_EMAIL = TypeAdapter(EmailStr)
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def decode_pdf_payload(encoded: str | None) -> bytes:
    if not encoded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O PDF do pedido é obrigatório para finalizar com envio automático.",
        )
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O PDF do pedido está em formato inválido.",
        ) from exc
    if len(content) > settings.ORDER_PDF_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="O PDF do pedido excede o limite permitido.",
        )
    if len(content) < 8 or not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O arquivo enviado não é um PDF completo.",
        )
    return content


def _normalized_email(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(_EMAIL.validate_python(value.strip())).lower()
    except ValidationError:
        return None


def _idempotency_key(
    order: Order, batch_number: int, recipient_kind: str, recipient_email: str | None
) -> str:
    recipient = recipient_email or recipient_kind
    digest = hashlib.sha256(recipient.encode("utf-8")).hexdigest()[:20]
    return f"order-finalized/{order.id}/v{order.document_version}/b{batch_number}/{digest}"


async def _parties(db: AsyncSession, order: Order) -> tuple[Client, Representative | None]:
    client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one()
    representative = None
    if order.rep_id:
        representative = (
            await db.execute(select(Representative).where(Representative.id == order.rep_id))
        ).scalar_one_or_none()
    return client, representative


async def _delivery_rows(
    db: AsyncSession,
    order: Order,
    document: OrderDocument,
    batch_number: int,
) -> list[OrderEmailDelivery]:
    client, representative = await _parties(db, order)
    raw = [("client", client.name, client.email)]
    if representative:
        raw.append(("representative", representative.name, representative.email))

    by_email: dict[str, tuple[list[str], list[str]]] = {}
    missing: list[tuple[str, str]] = []
    for kind, name, email_value in raw:
        email = _normalized_email(email_value)
        if not email:
            missing.append((kind, name))
            continue
        kinds, names = by_email.setdefault(email, ([], []))
        kinds.append(kind)
        names.append(name)

    now = datetime.now(timezone.utc)
    rows: list[OrderEmailDelivery] = []
    for email, (kinds, names) in by_email.items():
        kind = "client_and_representative" if len(kinds) > 1 else kinds[0]
        row = OrderEmailDelivery(
            id=uuid.uuid4(),
            order_id=order.id,
            document_id=document.id,
            recipient_kind=kind,
            recipient_name=" / ".join(dict.fromkeys(names)),
            recipient_email=email,
            status="pending",
            batch_number=batch_number,
            next_attempt_at=now,
            idempotency_key=_idempotency_key(order, batch_number, kind, email),
        )
        db.add(row)
        rows.append(row)
    for kind, name in missing:
        row = OrderEmailDelivery(
            id=uuid.uuid4(),
            order_id=order.id,
            document_id=document.id,
            recipient_kind=kind,
            recipient_name=name,
            recipient_email=None,
            status="missing_address",
            batch_number=batch_number,
            next_attempt_at=None,
            idempotency_key=_idempotency_key(order, batch_number, kind, None),
            last_error="E-mail ausente ou inválido no cadastro.",
        )
        db.add(row)
        rows.append(row)
    return rows


async def create_finalized_document(
    db: AsyncSession, order: Order, pdf_content: bytes
) -> tuple[OrderDocument, list[OrderEmailDelivery]]:
    sha256 = hashlib.sha256(pdf_content).hexdigest()
    key = document_key(order.market_code, order.id, order.document_version, sha256)
    client, _ = await _parties(db, order)
    safe_client = _SAFE_FILENAME.sub("_", client.name.strip()).strip("_") or "cliente"
    filename = f"{order.code}_{safe_client}.pdf"[:255]
    await persist_order_pdf(key, order.market_code, pdf_content)
    document = OrderDocument(
        id=uuid.uuid4(),
        order_id=order.id,
        market_code=order.market_code,
        document_version=order.document_version,
        storage_key=key,
        sha256=sha256,
        filename=filename,
        content_length=len(pdf_content),
    )
    db.add(document)
    rows = await _delivery_rows(db, order, document, 1)
    return document, rows


async def enqueue_manual_resend(
    db: AsyncSession, order: Order, document: OrderDocument
) -> list[OrderEmailDelivery]:
    last_batch = (
        await db.execute(
            select(func.coalesce(func.max(OrderEmailDelivery.batch_number), 0)).where(
                OrderEmailDelivery.order_id == order.id
            )
        )
    ).scalar_one()
    return await _delivery_rows(db, order, document, int(last_batch) + 1)
