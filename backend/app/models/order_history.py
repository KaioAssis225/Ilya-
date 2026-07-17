import uuid
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class OrderHistory(Base, TimestampMixin):
    __tablename__ = "order_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="history")
    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_order_history_created_id", "created_at", "id"),
        Index("ix_order_history_order_created_id", "order_id", "created_at", "id"),
        Index("ix_order_history_user_id", "user_id"),
    )
