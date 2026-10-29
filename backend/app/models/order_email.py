"""Documentos e entregas de e-mail de pedidos.

A fila é separada das integrações de estoque e do Moloni. O snapshot e os
destinatários ficam congelados para que novas tentativas reproduzam exatamente
o documento e a mensagem decididos na finalização.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class OrderEmailDocument(Base, TimestampMixin):
    __tablename__ = "order_email_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        UniqueConstraint("order_id", "version", name="uq_order_email_documents_order_version"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_order_email_document_status",
        ),
        Index("ix_order_email_documents_due", "status", "next_attempt_at", "created_at"),
    )


class OrderEmailDelivery(Base, TimestampMixin):
    __tablename__ = "order_email_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code", ondelete="RESTRICT"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_email_documents.id", ondelete="RESTRICT"), nullable=False)
    recipient_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(320))
    recipient_name: Mapped[str | None] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    resend_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_email_deliveries.id", ondelete="RESTRICT"))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_type: Mapped[str | None] = mapped_column(String(80))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'accepted', 'delivered', 'failed', 'needs_review', 'blocked', 'skipped')",
            name="ck_order_email_delivery_status",
        ),
        CheckConstraint(
            "origin IN ('finalization', 'manual_resend')",
            name="ck_order_email_delivery_origin",
        ),
        Index("ix_order_email_deliveries_order_created", "order_id", "created_at", "id"),
        Index("ix_order_email_deliveries_due", "status", "next_attempt_at", "created_at"),
        Index(
            "uq_order_email_finalization_recipient",
            "document_id",
            func.lower(recipient_email),
            unique=True,
            postgresql_where=text("origin = 'finalization' AND recipient_email IS NOT NULL AND recipient_email <> ''"),
        ),
    )


class OrderEmailWebhookEvent(Base, TimestampMixin):
    __tablename__ = "order_email_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    svix_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_email_deliveries.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("ix_order_email_webhook_message", "provider_message_id", "applied_at"),
    )
