import uuid
from decimal import Decimal
from sqlalchemy import CheckConstraint, String, Numeric, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Representative(Base, TimestampMixin):
    __tablename__ = "representatives"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    cep: Mapped[str] = mapped_column(String(20), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    max_discount: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("15.00"))

    __table_args__ = (
        CheckConstraint(
            "state ~ '^[A-Z]{2}$'",
            name="ck_representatives_state_uf",
        ),
        Index("ix_representatives_name_id", "name", "id"),
        Index(
            "ix_representatives_name_lower_id",
            func.lower(name),
            "id",
        ),
        Index("ix_representatives_email_id", "email", "id"),
        Index(
            "uq_representatives_email_lower",
            func.lower(email),
            unique=True,
        ),
        Index("ix_representatives_phone_id", "phone", "id"),
        Index("ix_representatives_city_id", "city", "id"),
        Index("ix_representatives_state_id", "state", "id"),
        Index(
            "ix_representatives_max_discount_id",
            "max_discount",
            "id",
        ),
        Index(
            "ix_representatives_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_representatives_email_trgm",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
        Index(
            "ix_representatives_city_trgm",
            "city",
            postgresql_using="gin",
            postgresql_ops={"city": "gin_trgm_ops"},
        ),
    )
