import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=List[NotificationRead])
async def list_notifications(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    notif.is_read = True
    await db.commit()
    await db.refresh(notif)
    return notif
