import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, DateTime, String, Text, Numeric, Integer, Boolean, ForeignKey, Index, JSON, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order_history import OrderHistory


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR")
    price_list_code: Mapped[str] = mapped_column(String(30), nullable=False, default="lojista", server_default="lojista")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL", server_default="BRL")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="pt-BR", server_default="pt-BR")
    # O código PED é sequencial dentro do usuário que criou o pedido.
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    number_owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    orc_id: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id"), nullable=True)
    total_value: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total_ipi: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total_with_ipi: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rep_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Migration/01: frescor para consumidores externos (leitura cross-database
    # do Ilya Estoque).
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    history: Mapped[list["OrderHistory"]] = relationship("OrderHistory", back_populates="order", cascade="all, delete-orphan", lazy="selectin", order_by="OrderHistory.created_at")

    __table_args__ = (
        CheckConstraint(
            "NOT (is_finalized AND is_cancelled)",
            name="ck_orders_single_terminal_status",
        ),
        CheckConstraint(
            "is_finalized = (finalized_at IS NOT NULL)",
            name="ck_orders_finalized_timestamp",
        ),
        CheckConstraint(
            "is_cancelled = (cancelled_at IS NOT NULL)",
            name="ck_orders_cancelled_timestamp",
        ),
        CheckConstraint(
            "order_number > 0",
            name="ck_orders_order_number_positive",
        ),
        UniqueConstraint(
            "market_code", "number_owner_id",
            "order_number",
            name="uq_orders_market_owner_order_number",
        ),
        UniqueConstraint("market_code", "orc_id", name="uq_orders_market_orc_id"),
        Index("ix_orders_market_created_id", "market_code", "created_at", "id"),
        Index("ix_orders_number_owner_id", "number_owner_id"),
        Index(
            "ix_orders_code_trgm",
            "code",
            postgresql_using="gin",
            postgresql_ops={"code": "gin_trgm_ops"},
        ),
        Index(
            "ix_orders_orc_id_trgm",
            "orc_id",
            postgresql_using="gin",
            postgresql_ops={"orc_id": "gin_trgm_ops"},
        ),
        Index("ix_orders_created_id", "created_at", "id"),
        Index("ix_orders_client_created_id", "client_id", "created_at", "id"),
        Index(
            "ix_orders_rep_created_id",
            "rep_id",
            "created_at",
            "id",
            postgresql_where=text("rep_id IS NOT NULL"),
        ),
        Index(
            "ix_orders_open_created_id",
            "created_at",
            "id",
            postgresql_where=text("is_finalized = false AND is_cancelled = false"),
        ),
        Index(
            "ix_orders_finalized_created_id",
            "created_at",
            "id",
            postgresql_where=text("is_finalized = true"),
        ),
        Index(
            "ix_orders_cancelled_created_id",
            "created_at",
            "id",
            postgresql_where=text("is_cancelled = true"),
        ),
        Index(
            "ix_orders_retention_open_updated_id",
            "updated_at",
            "id",
            postgresql_where=text(
                "is_finalized = false AND is_cancelled = false"
            ),
        ),
        Index(
            "ix_orders_retention_finalized_at_id",
            "finalized_at",
            "id",
            postgresql_where=text("is_finalized = true"),
        ),
        Index(
            "ix_orders_retention_cancelled_at_id",
            "cancelled_at",
            "id",
            postgresql_where=text("is_cancelled = true"),
        ),
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
    ipi_value: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    tax_label: Mapped[str] = mapped_column(String(10), nullable=False, default="IPI", server_default="IPI")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL", server_default="BRL")
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")

    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
    )
