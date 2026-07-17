import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index(
            "ix_notifications_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_notifications_unread_user_created",
            "user_id",
            "created_at",
            postgresql_where=text("is_read IS FALSE"),
        ),
    )
