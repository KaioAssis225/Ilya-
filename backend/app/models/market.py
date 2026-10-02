import uuid
from decimal import Decimal

from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


BR_MARKET = "BR"
EU_MARKET = "EU"

# Estados do IVA europeu por SKU. A taxa só é faturável depois de aprovada
# manualmente por uma pessoa; `pending` é o estado inicial (inclusive para o
# legado) e `rejected` marca taxa recusada na revisão fiscal.
VAT_PENDING = "pending"
VAT_APPROVED = "approved"
VAT_REJECTED = "rejected"

# Procedência da taxa. O legado não tem como provar origem aprovada, então
# fica `legacy_unknown`; toda taxa vinda do import nasce `import` e pendente.
VAT_SOURCE_LEGACY = "legacy_unknown"
VAT_SOURCE_IMPORT = "import"


class Market(Base, TimestampMixin):
    __tablename__ = "markets"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    tax_label: Mapped[str] = mapped_column(String(10), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UserMarket(Base, TimestampMixin):
    __tablename__ = "user_markets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code", ondelete="CASCADE"), primary_key=True
    )
    # R2a: autoridade de vínculo comercial por mercado. `role` nullable enquanto
    # status='pending'. As FKs usam RESTRICT para não deixar um papel ativo sem
    # o registro comercial que lhe dá significado.
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    linked_client_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
    rep_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )
    can_view_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_approve_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["linked_client_id", "market_code"],
            ["clients.id", "clients.market_code"],
            name="fk_user_markets_client_same_market",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rep_id", "market_code"],
            ["representatives.id", "representatives.market_code"],
            name="fk_user_markets_rep_same_market",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended')",
            name="ck_user_markets_status",
        ),
        CheckConstraint(
            "role IS NULL OR role IN "
            "('admin', 'vendedor', 'representante', 'cadastros', "
            "'produtos', 'cliente', 'executivo')",
            name="ck_user_markets_role",
        ),
        CheckConstraint(
            "status != 'active' OR role IS NOT NULL",
            name="ck_user_markets_active_role",
        ),
        CheckConstraint(
            "(role IS NULL AND linked_client_id IS NULL AND rep_id IS NULL) OR "
            "(role = 'cliente' AND linked_client_id IS NOT NULL AND rep_id IS NULL) OR "
            "(role = 'representante' AND rep_id IS NOT NULL AND linked_client_id IS NULL) OR "
            "(role IN ('admin', 'vendedor', 'cadastros', 'produtos', 'executivo') "
            "AND linked_client_id IS NULL AND rep_id IS NULL)",
            name="ck_user_markets_role_links",
        ),
        Index(
            "uq_user_markets_client_per_market",
            "market_code",
            "linked_client_id",
            unique=True,
            postgresql_where=linked_client_id.is_not(None),
        ),
        Index(
            "uq_user_markets_rep_per_market",
            "market_code",
            "rep_id",
            unique=True,
            postgresql_where=rep_id.is_not(None),
        ),
    )


class PriceList(Base, TimestampMixin):
    __tablename__ = "price_lists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("market_code", "code", name="uq_price_lists_market_code"),
        Index("ix_price_lists_market_active", "market_code", "is_active"),
    )


class ProductMarket(Base, TimestampMixin):
    __tablename__ = "product_markets"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code", ondelete="CASCADE"), primary_key=True
    )
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Governança fiscal do IVA (Portugal). A taxa não basta: ela só é faturável
    # quando `vat_status == approved`, com autor e data da aprovação. BR não usa
    # estes campos (segue com IPI do grupo) e fica `pending` sem efeito algum.
    vat_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=VAT_PENDING
    )
    vat_source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=VAT_SOURCE_LEGACY
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nomes comerciais pertencem ao mercado. O catálogo-base continua único,
    # mas Portugal pode usar terminologia pt-PT e uma versão inglesa sem
    # alterar a descrição brasileira.
    description_pt_pt: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)", name="ck_product_markets_vat"),
        # Aprovação é indivisível: só existe autor+data quando `approved`, e
        # `approved` exige a taxa definida. Assim o legado fica `pending` sem
        # forjar origem aprovada, e ninguém grava autor/data sem aprovar.
        CheckConstraint(
            "(vat_status = 'approved' AND vat_rate IS NOT NULL "
            "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL) "
            "OR (vat_status IN ('pending', 'rejected') "
            "AND approved_by_user_id IS NULL AND approved_at IS NULL)",
            name="ck_product_markets_vat_approval",
        ),
        Index("ix_product_markets_market_available", "market_code", "is_available"),
    )


class ProductPrice(Base, TimestampMixin):
    __tablename__ = "product_prices"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    price_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("price_lists.id", ondelete="CASCADE"), primary_key=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_product_prices_non_negative"),
        Index("ix_product_prices_list_product", "price_list_id", "product_id"),
    )


class MarketTaxRate(Base, TimestampMixin):
    __tablename__ = "market_tax_rates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate <= 100", name="ck_market_tax_rates_range"),
        UniqueConstraint("market_code", "product_type", name="uq_market_tax_rates_market_type"),
    )


class MarketOrderCounter(Base):
    __tablename__ = "market_order_counters"

    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), primary_key=True)
    number_owner_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (CheckConstraint("next_value > 0", name="ck_market_order_counters_positive"),)


class MarketQuoteCounter(Base):
    __tablename__ = "market_quote_counters"

    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (CheckConstraint("next_value > 0", name="ck_market_quote_counters_positive"),)


# R2a: capacidades de plataforma separadas de qualquer mercado. Autoridade
# distinta de user_markets — sessão de plataforma não tem active_market.
# Sem grants iniciais: a conta inicial será concedida nominalmente após deploy.
PLATFORM_CAPABILITIES = ("platform_admin", "activate_market", "read_outbox")


class UserPlatformPermission(Base, TimestampMixin):
    __tablename__ = "user_platform_permissions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(String(50), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "capability IN ('platform_admin', 'activate_market', 'read_outbox')",
            name="ck_user_platform_permissions_capability",
        ),
    )
