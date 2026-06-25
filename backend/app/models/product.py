import uuid
from sqlalchemy import String, Text, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    altura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    largura: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    profundidade: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    opt_aluminio: Mapped[str | None] = mapped_column(String(50), nullable=True)
    opt_tecido: Mapped[str | None] = mapped_column(String(50), nullable=True)
    opt_corda: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_products_product_code", "product_code"),
    )
