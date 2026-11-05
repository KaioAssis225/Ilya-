import uuid

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ClientContact(Base, TimestampMixin):
    """Contato adicional de um cliente (além do contato principal da ficha).

    Pertence ao cliente: some junto com ele (ON DELETE CASCADE) e é apagado na
    anonimização, porque nome, telefone e e-mail são dados pessoais.
    """

    __tablename__ = "client_contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ordem em que o usuário montou a lista.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        Index("ix_client_contacts_client_position", "client_id", "position"),
    )
