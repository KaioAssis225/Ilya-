import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Numeric, Integer, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order_history import OrderHistory


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    orc_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id"), nullable=True)
    total_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_ipi: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_with_ipi: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rep_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    history: Mapped[list["OrderHistory"]] = relationship("OrderHistory", back_populates="order", cascade="all, delete-orphan", lazy="selectin", order_by="OrderHistory.created_at")

    __table_args__ = (
        Index("ix_orders_code", "code"),
        Index("ix_orders_orc_id", "orc_id"),
    )

    # Flags derivadas — permitem a listagem informar status de assinatura
    # sem transportar o blob base64 (~750 KB por assinatura) (V-M7).
    @property
    def rep_signed(self) -> bool:
        return self.rep_signature is not None

    @property
    def client_signed(self) -> bool:
        return self.client_signature is not None


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
    # Categoria -> cor escolhida, dinâmico (código de categoria vem de OptionalCategory.code).
    # Substitui as antigas colunas fixas opt_aluminio/madeira/tecido/couro/corda,
    # que só suportavam os 8 códigos originais de teste (V-Bloco65-cats).
    opt_categories: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    ipi_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    ipi_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
