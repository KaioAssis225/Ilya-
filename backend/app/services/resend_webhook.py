from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.order_email import OrderEmailDelivery, ResendWebhookEvent


EVENT_STATUS = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.failed": "failed",
    "email.suppressed": "suppressed",
    "email.bounced": "bounced",
    "email.complained": "complained",
}
TERMINAL_STATUSES = {"delivered", "failed", "suppressed", "bounced", "complained"}


def _transition_delivery(
    delivery: OrderEmailDelivery,
    event_type: str,
    data: dict | None = None,
) -> None:
    mapped_status = EVENT_STATUS.get(event_type)
    if not mapped_status:
        return
    if delivery.status in TERMINAL_STATUSES and mapped_status not in TERMINAL_STATUSES:
        return
    delivery.status = mapped_status
    if mapped_status == "delivered":
        delivery.delivered_at = datetime.now(timezone.utc)
        delivery.last_error = None
    elif mapped_status in {"failed", "suppressed", "bounced", "complained"}:
        payload = data or {}
        detail = payload.get("bounce") or payload.get("failed") or payload.get("complaint")
        delivery.last_error = json.dumps(detail, ensure_ascii=False)[:500] if detail else event_type


def verify_signature(
    raw_body: bytes,
    event_id: str | None,
    timestamp: str | None,
    signature_header: str | None,
    *,
    now: int | None = None,
) -> None:
    if not settings.RESEND_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook não configurado.")
    if not event_id or not timestamp or not signature_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assinatura do webhook ausente.")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Timestamp do webhook inválido.") from exc
    current = int(time.time()) if now is None else now
    if abs(current - timestamp_value) > settings.RESEND_WEBHOOK_TOLERANCE_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook expirado.")

    encoded_secret = settings.RESEND_WEBHOOK_SECRET.removeprefix("whsec_")
    try:
        padding = "=" * (-len(encoded_secret) % 4)
        secret = base64.b64decode(encoded_secret + padding, altchars=b"-_")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Segredo do webhook inválido.") from exc
    signed = event_id.encode() + b"." + timestamp.encode() + b"." + raw_body
    expected = base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest()).decode("ascii")
    candidates = [part.split(",", 1)[1] for part in signature_header.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assinatura do webhook inválida.")


async def apply_event(
    db: AsyncSession, event_id: str, raw_body: bytes
) -> bool:
    if (
        await db.execute(select(ResendWebhookEvent.id).where(ResendWebhookEvent.event_id == event_id))
    ).scalar_one_or_none() is not None:
        return False
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload do webhook inválido.") from exc
    event_type = payload.get("type")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_message_id = data.get("email_id")
    if not isinstance(event_type, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de evento ausente.")
    if provider_message_id is not None and not isinstance(provider_message_id, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Identificador de e-mail inválido.")

    db.add(
        ResendWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            provider_message_id=provider_message_id,
        )
    )
    if EVENT_STATUS.get(event_type) and provider_message_id:
        delivery = (
            await db.execute(
                select(OrderEmailDelivery)
                .where(OrderEmailDelivery.provider_message_id == provider_message_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if delivery:
            _transition_delivery(delivery, event_type, data)
    await db.commit()
    return True


async def reconcile_delivery_events(db: AsyncSession, delivery_id) -> None:
    """Fecha a corrida em que o webhook chega antes do ID do Resend ser salvo."""
    delivery = (
        await db.execute(
            select(OrderEmailDelivery)
            .where(OrderEmailDelivery.id == delivery_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if delivery is None or not delivery.provider_message_id:
        return
    events = list(
        (
            await db.execute(
                select(ResendWebhookEvent)
                .where(ResendWebhookEvent.provider_message_id == delivery.provider_message_id)
                .order_by(ResendWebhookEvent.received_at, ResendWebhookEvent.id)
            )
        ).scalars()
    )
    for event in events:
        _transition_delivery(delivery, event.event_type)
