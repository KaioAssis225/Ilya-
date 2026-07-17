import uuid
from sqlalchemy import String, Table, Column, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

product_optionals = Table(
    "product_optionals",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("optional_id", ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
)


class OptionalColor(Base, TimestampMixin):
    __tablename__ = "optionals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    color_name: Mapped[str] = mapped_column(String(100), nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
