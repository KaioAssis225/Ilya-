import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, String, ForeignKey, Numeric, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False, default="BR", server_default="BR")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Só dígitos (ver core.documents): duas grafias do mesmo documento furariam
    # o índice único. Nulo porque o campo é opcional e porque os cadastros
    # anteriores a ele não têm o dado.
    cpf_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    cep: Mapped[str] = mapped_column(String(20), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    price_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="lojista")
    price_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("price_lists.id"), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="BR", server_default="BR")
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id", ondelete="SET NULL"), nullable=True)
    max_discount: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "market_code <> 'BR' OR state ~ '^[A-Z]{2}$'",
            name="ck_clients_state_uf",
        ),
        Index("ix_clients_rep_id", "rep_id"),
        Index("ix_clients_market_id", "market_code", "id"),
        Index("ix_clients_created_by_user_id", "created_by_user_id"),
        Index("ix_clients_state_id", "state", "id"),
        Index("ix_clients_name_id", "name", "id"),
        Index("ix_clients_email_id", "email", "id"),
        Index(
            "uq_clients_market_email_lower",
            "market_code", func.lower(email),
            unique=True,
        ),
        Index("uq_clients_market_cpf_cnpj", "market_code", "cpf_cnpj", unique=True),
        Index("ix_clients_phone_id", "phone", "id"),
        Index("ix_clients_city_id", "city", "id"),
        Index("ix_clients_max_discount_id", "max_discount", "id"),
        Index("ix_clients_retention_activity_id", "last_activity_at", "id"),
        Index(
            "ix_clients_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_clients_email_trgm",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
        Index(
            "ix_clients_city_trgm",
            "city",
            postgresql_using="gin",
            postgresql_ops={"city": "gin_trgm_ops"},
        ),
    )


def anonymize_client_fields(client: Client) -> None:
    """Anonimiza os campos PII do cliente (LGPD Art. 18, IV) preservando o
    registro para integridade fiscal dos pedidos vinculados (Art. 16, I).
    Usado tanto pelo fluxo self-service (/auth/anonymize) quanto pelo admin."""
    client.name = "CLIENTE ANONIMIZADO"
    client.cpf_cnpj = None
    client.phone = "(00) 00000-0000"
    client.email = f"anonimizado_{client.id}@excluido.ilya"
    client.cep = "00000-000"
    client.numero = None
    client.address = "Endereço Excluído, 00"
    client.city = "—"
    client.state = "EX"
