import uuid
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class OptionalCategory(Base):
    __tablename__ = "optional_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
