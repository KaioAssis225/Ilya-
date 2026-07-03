import uuid
from sqlalchemy import String, Text, Numeric, Boolean, Integer, ForeignKey, Index, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from app.models.base import Base, TimestampMixin
from app.models.optional_color import product_optionals, OptionalColor

product_set_component_optionals = Table(
    "product_set_component_optionals",
    Base.metadata,
    Column("component_id", PGUUID(as_uuid=True), ForeignKey("product_set_components.id", ondelete="CASCADE"), primary_key=True),
    Column("optional_id", PGUUID(as_uuid=True), ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Outro")
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price_lojista: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price_corporativo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    all_optionals_categories: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    optionals: Mapped[list["OptionalColor"]] = relationship(
        "OptionalColor", secondary=product_optionals, lazy="selectin"
    )
    set_items: Mapped[list["ProductSetItem"]] = relationship(
        "ProductSetItem", foreign_keys="ProductSetItem.set_id",
        cascade="all, delete-orphan", lazy="selectin",
    )
    components: Mapped[list["ProductSetComponent"]] = relationship(
        "ProductSetComponent", foreign_keys="ProductSetComponent.set_id",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_products_product_code", "product_code"),
    )


class ProductSetItem(Base, TimestampMixin):
    __tablename__ = "product_set_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id], lazy="selectin")

    __table_args__ = (
        Index("ix_product_set_items_set_id", "set_id"),
    )


class ProductSetComponent(Base, TimestampMixin):
    __tablename__ = "product_set_components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    optionals: Mapped[list["OptionalColor"]] = relationship(
        "OptionalColor", secondary=product_set_component_optionals, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_product_set_components_set_id", "set_id"),
    )
