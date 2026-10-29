"""Webhook público do Resend, autenticado exclusivamente pela assinatura Svix."""
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import settings
from app.core.limiter import limiter
from app.core.resend_webhook import verify_resend_signature
from app.models.order_email import OrderEmailDelivery, OrderEmailWebhookEvent
from app.services.order_email_events import apply_event, parse_event_time


router = APIRouter(tags=["webhooks"])
_EVENT_TYPE_RE = re.compile(r"^[a-z0-9._-]{1,80}$")
_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


@router.post("/webhooks/resend")
@limiter.limit("60/minute")
async def receive_resend_webhook(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    # Webhook de conta compartilhada não pertence a um mercado de sessão.
    db.sync_session.info.pop("active_market", None)
    body = await request.body()
    if not settings.RESEND_WEBHOOK_SECRET:
        return JSONResponse(status_code=503, content={"detail": "Webhook indisponível."})
    svix_id = request.headers.get("svix-id", "")
    timestamp = request.headers.get("svix-timestamp", "")
    signature = request.headers.get("svix-signature", "")
    if not verify_resend_signature(
        settings.RESEND_WEBHOOK_SECRET,
        svix_id,
        timestamp,
        body,
        signature,
    ):
        return JSONResponse(status_code=401, content={"detail": "Assinatura inválida."})
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"detail": "Corpo inválido."})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"detail": "Corpo inválido."})
    event_type = payload.get("type")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_message_id = data.get("email_id") or data.get("id")
    if (
        not isinstance(event_type, str)
        or not _EVENT_TYPE_RE.fullmatch(event_type)
        or not isinstance(provider_message_id, str)
        or not _MESSAGE_ID_RE.fullmatch(provider_message_id)
    ):
        return {"ok": True}

    received_at = datetime.now(timezone.utc)
    event_at = parse_event_time(payload.get("created_at"), received_at)
    event_id = uuid.uuid4()
    inserted = (
        await db.execute(
            insert(OrderEmailWebhookEvent)
            .values(
                id=event_id,
                svix_id=svix_id,
                event_type=event_type,
                provider_message_id=provider_message_id,
                received_at=received_at,
                payload_summary={
                    "type": event_type,
                    "message_id": provider_message_id,
                    "timestamp": event_at.isoformat(),
                },
            )
            .on_conflict_do_nothing(
                index_elements=[OrderEmailWebhookEvent.svix_id]
            )
            .returning(OrderEmailWebhookEvent.id)
        )
    ).scalar_one_or_none()
    if inserted is None:
        await db.commit()
        return {"ok": True}

    event = await db.get(OrderEmailWebhookEvent, event_id)
    delivery = (
        await db.execute(
            select(OrderEmailDelivery)
            .where(
                OrderEmailDelivery.provider_message_id == provider_message_id
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if delivery is not None and event is not None:
        apply_event(
            delivery,
            event,
            event_at=event_at,
        )
    await db.commit()
    return {"ok": True}
