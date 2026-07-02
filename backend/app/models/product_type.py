import uuid
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product_group import ProductGroup


class ProductType(Base):
    __tablename__ = "product_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("product_groups.id"), nullable=True)
    group: Mapped[Optional["ProductGroup"]] = relationship("ProductGroup", lazy="selectin")
