import uuid
from decimal import Decimal

from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


BR_MARKET = "BR"
EU_MARKET = "EU"


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

    __table_args__ = (
        CheckConstraint("vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)", name="ck_product_markets_vat"),
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
