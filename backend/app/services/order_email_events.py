"""Aplica eventos Resend sem permitir regressão de estado."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_email import OrderEmailDelivery, OrderEmailWebhookEvent


_TERMINAL = {"delivered", "failed"}
_KNOWN_EVENTS = {
    "email.delivered",
    "email.bounced",
    "email.failed",
    "email.complained",
    "email.delivery_delayed",
}


def parse_event_time(value: object, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return fallback


def apply_event(
    delivery: OrderEmailDelivery,
    event: OrderEmailWebhookEvent,
    *,
    event_at: datetime,
) -> None:
    """O primeiro resultado terminal vence; eventos tardios nunca o trocam.

    Assim um bounce não vira entregue por atraso de ordenação, e uma entrega
    confirmada não volta a aceita ou falha. Eventos informativos só atualizam
    os metadados quando forem mais novos que o último observado.
    """
    if event.event_type in _KNOWN_EVENTS and (
        delivery.last_event_at is None or event_at >= delivery.last_event_at
    ):
        delivery.last_event_type = event.event_type
        delivery.last_event_at = event_at
    if delivery.status not in _TERMINAL:
        if event.event_type == "email.delivered":
            delivery.status = "delivered"
            delivery.delivered_at = event_at
            delivery.last_error = None
        elif event.event_type == "email.bounced":
            delivery.status = "failed"
            delivery.last_error = "bounced"
        elif event.event_type == "email.failed":
            delivery.status = "failed"
            delivery.last_error = "provider_failed"
    event.delivery_id = delivery.id
    event.applied_at = datetime.now(timezone.utc)


async def apply_orphan_events(
    db: AsyncSession,
    delivery: OrderEmailDelivery,
) -> None:
    rows = (
        await db.execute(
            select(OrderEmailWebhookEvent)
            .where(
                OrderEmailWebhookEvent.provider_message_id
                == delivery.provider_message_id,
                OrderEmailWebhookEvent.applied_at.is_(None),
            )
            .order_by(OrderEmailWebhookEvent.received_at, OrderEmailWebhookEvent.id)
            .with_for_update()
        )
    ).scalars().all()
    for event in rows:
        apply_event(
            delivery,
            event,
            event_at=parse_event_time(
                event.payload_summary.get("timestamp"), event.received_at
            ),
        )


async def apply_pending_events(db: AsyncSession, *, limit: int = 20) -> int:
    """Reaplica eventos órfãos cuja entrega já tenha o id do provedor."""
    rows = (
        await db.execute(
            select(OrderEmailWebhookEvent, OrderEmailDelivery)
            .join(
                OrderEmailDelivery,
                OrderEmailDelivery.provider_message_id
                == OrderEmailWebhookEvent.provider_message_id,
            )
            .where(OrderEmailWebhookEvent.applied_at.is_(None))
            .order_by(
                OrderEmailWebhookEvent.received_at,
                OrderEmailWebhookEvent.id,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for event, delivery in rows:
        apply_event(
            delivery,
            event,
            event_at=parse_event_time(
                event.payload_summary.get("timestamp"), event.received_at
            ),
        )
    return len(rows)
