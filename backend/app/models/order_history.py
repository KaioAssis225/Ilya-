import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import DateTime, String, Text, ForeignKey, Index, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class OrderHistory(Base, TimestampMixin):
    __tablename__ = "order_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # O instante vem da aplicação, não de `now()` do banco: `now()` é o início da
    # TRANSAÇÃO, então eventos gravados na mesma transação (os testes de integração
    # rodam tudo numa só) ficavam com `created_at` idêntico e a ordem do histórico
    # (criado → editado → finalizado) virava acaso do plano de consulta. O
    # `server_default` continua para inserções que não passam pelo ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, server_default=func.now(), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    items_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="history")
    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_order_history_created_id", "created_at", "id"),
        Index("ix_order_history_order_created_id", "order_id", "created_at", "id"),
        Index("ix_order_history_user_id", "user_id"),
    )
