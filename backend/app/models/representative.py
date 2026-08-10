import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, String, Numeric, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Representative(Base, TimestampMixin):
    __tablename__ = "representatives"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ver Client.cpf_cnpj: só dígitos, nulo para o cadastro legado. Tabelas
    # separadas por decisão — a mesma pessoa pode ser cliente e representante.
    cpf_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    cep: Mapped[str] = mapped_column(String(20), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    max_discount: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("30.00"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    relationship_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    __table_args__ = (
        CheckConstraint(
            "state ~ '^[A-Z]{2}$'",
            name="ck_representatives_state_uf",
        ),
        Index("ix_representatives_name_id", "name", "id"),
        Index("ix_representatives_created_by_user_id", "created_by_user_id"),
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
        Index("uq_representatives_cpf_cnpj", "cpf_cnpj", unique=True),
        Index("ix_representatives_phone_id", "phone", "id"),
        Index("ix_representatives_city_id", "city", "id"),
        Index("ix_representatives_state_id", "state", "id"),
        Index(
            "ix_representatives_retention_end_id",
            "relationship_ended_at",
            "id",
            postgresql_where=text("relationship_ended_at IS NOT NULL"),
        ),
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


def anonymize_representative_fields(representative: Representative) -> None:
    """Remove PII sem quebrar pedidos e clientes historicamente vinculados."""
    representative.name = "REPRESENTANTE ANONIMIZADO"
    representative.cpf_cnpj = None
    representative.phone = "(00) 00000-0000"
    representative.email = f"anonimizado_{representative.id}@excluido.ilya"
    representative.cep = "00000-000"
    representative.numero = None
    representative.address = "ENDEREÇO ANONIMIZADO"
    representative.city = "NÃO INFORMADO"
    representative.state = "EX"
