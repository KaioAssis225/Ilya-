import uuid
from sqlalchemy import String, Text, Numeric, Integer, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    orc_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id"), nullable=True)
    total_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rep_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_orders_code", "code"),
        Index("ix_orders_orc_id", "orc_id"),
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)

    # Snapshot histórico — cópia dos dados do produto no momento da venda
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    opt_aluminio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opt_madeira: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opt_tecido: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opt_couro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opt_corda: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
