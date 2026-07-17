import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    cep: Mapped[str] = mapped_column(String(20), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    price_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="lojista")
    rep_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("representatives.id", ondelete="SET NULL"), nullable=True)
    max_discount: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))


def anonymize_client_fields(client: Client) -> None:
    """Anonimiza os campos PII do cliente (LGPD Art. 18, IV) preservando o
    registro para integridade fiscal dos pedidos vinculados (Art. 16, I).
    Usado tanto pelo fluxo self-service (/auth/anonymize) quanto pelo admin."""
    client.name = "CLIENTE ANONIMIZADO"
    client.phone = "(00) 00000-0000"
    client.email = f"anonimizado_{client.id}@excluido.ilya"
    client.cep = "00000-000"
    client.numero = None
    client.address = "Endereço Excluído, 00"
    client.city = "—"
    client.state = "EX"
