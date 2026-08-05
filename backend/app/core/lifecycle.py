import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client


async def touch_client_activity(
    db: AsyncSession,
    client_id: uuid.UUID,
    occurred_at: datetime | None = None,
) -> datetime:
    """Registra uso legítimo do cadastro para iniciar a retenção no marco correto."""
    activity_at = occurred_at or datetime.now(timezone.utc)
    await db.execute(
        update(Client)
        .where(Client.id == client_id)
        .values(last_activity_at=activity_at)
    )
    return activity_at
