import uuid
from sqlalchemy import String, Table, Column, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

product_optionals = Table(
    "product_optionals",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("optional_id", ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_product_optionals_optional_id", "optional_id"),
)


class OptionalColor(Base, TimestampMixin):
    __tablename__ = "optionals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR"
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    color_name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str] = mapped_column(String(4), nullable=False, default="ILYA", server_default="ILYA")
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint("brand IN ('ILYA', 'IBTW')", name="ck_optionals_brand"),
        Index(
            "ix_optionals_category_color_id",
            "category",
            "color_name",
            "id",
        ),
        Index("ix_optionals_market_category_id", "market_code", "category", "id"),
    )
