"""Independent uses of a master optional category on a product or set component."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Table, Column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


optional_application_allowed = Table(
    "optional_application_allowed",
    Base.metadata,
    Column("application_id", PGUUID(as_uuid=True), ForeignKey("product_optional_applications.id", ondelete="CASCADE"), primary_key=True),
    Column("optional_id", PGUUID(as_uuid=True), ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_optional_application_allowed_optional", "optional_id"),
)


class ProductOptionalApplication(Base):
    __tablename__ = "product_optional_applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_set_components.id", ondelete="CASCADE"), nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("optional_categories.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_repeat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category = relationship("OptionalCategory", lazy="selectin")
    allowed_optionals = relationship("OptionalColor", secondary=optional_application_allowed, lazy="selectin")

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_optional_application_name"),
        CheckConstraint("display_order >= 0", name="ck_optional_application_order"),
        Index("ix_optional_applications_product", "product_id", "display_order", "id"),
        Index("ix_optional_applications_component", "component_id"),
    )


class OrderItemOptionalChoice(Base):
    __tablename__ = "order_item_optional_choices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_optional_applications.id", ondelete="SET NULL"), nullable=True)
    optional_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("optionals.id", ondelete="SET NULL"), nullable=True)
    application_name: Mapped[str] = mapped_column(String(120), nullable=False)
    application_name_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_code: Mapped[str] = mapped_column(String(50), nullable=False)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    optional_name: Mapped[str] = mapped_column(String(100), nullable=False)
    component_name: Mapped[str | None] = mapped_column(String(20000), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_order_item_optional_choices_item", "order_item_id", "display_order", "id"),)
