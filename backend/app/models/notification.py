import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR")
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "is_read = (read_at IS NOT NULL)",
            name="ck_notifications_read_timestamp",
        ),
        Index(
            "ix_notifications_user_created",
            "user_id",
            "created_at",
        ),
        Index("ix_notifications_market_user_created", "market_code", "user_id", "created_at"),
        Index(
            "ix_notifications_unread_user_created",
            "user_id",
            "created_at",
            postgresql_where=text("is_read IS FALSE"),
        ),
        Index(
            "ix_notifications_retention_read_id",
            "read_at",
            "id",
            postgresql_where=text("is_read IS TRUE"),
        ),
        Index(
            "ix_notifications_retention_unread_id",
            "created_at",
            "id",
            postgresql_where=text("is_read IS FALSE"),
        ),
    )
