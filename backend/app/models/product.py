import uuid
from sqlalchemy import String, Text, Numeric, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.optional_color import product_optionals, OptionalColor


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_circular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    optionals: Mapped[list["OptionalColor"]] = relationship(
        "OptionalColor", secondary=product_optionals, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_products_product_code", "product_code"),
    )
