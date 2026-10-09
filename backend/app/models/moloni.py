"""Persistência da integração Moloni.

Tokens nunca são guardados em texto. O worker guarda somente referências do
pedido e faz o mapeamento no momento da entrega, preservando o pedido finalizado
como a fonte comercial do documento.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MoloniConnection(Base, TimestampMixin):
    __tablename__ = "moloni_connections"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MoloniOAuthState(Base):
    __tablename__ = "moloni_oauth_states"
    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MoloniTaxMapping(Base):
    __tablename__ = "moloni_tax_mappings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("moloni_connections.id", ondelete="CASCADE"), nullable=False)
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    moloni_tax_id: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("connection_id", "vat_rate", name="uq_moloni_tax_connection_rate"),)

class MoloniCustomerLink(Base, TimestampMixin):
    __tablename__ = "moloni_customer_links"
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("moloni_connections.id", ondelete="CASCADE"), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), primary_key=True)
    moloni_customer_id: Mapped[int] = mapped_column(Integer, nullable=False)

class MoloniProductLink(Base, TimestampMixin):
    __tablename__ = "moloni_product_links"
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("moloni_connections.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    moloni_product_id: Mapped[int] = mapped_column(Integer, nullable=False)


class MoloniExportJob(Base, TimestampMixin):
    __tablename__ = "moloni_export_jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    moloni_document_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_moloni_export_jobs_order"),
        CheckConstraint("status IN ('pending', 'processing', 'delivered', 'dead_letter')", name="ck_moloni_export_job_status"),
    )
