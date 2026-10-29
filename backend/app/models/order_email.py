import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


DELIVERY_STATUSES = (
    "missing_address", "pending", "processing", "accepted", "sent",
    "delivered", "delayed", "failed", "bounced", "complained", "suppressed",
)


class OrderDocument(Base, TimestampMixin):
    __tablename__ = "order_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    market_code: Mapped[str] = mapped_column(String(2), nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_length: Mapped[int] = mapped_column(BigInteger, nullable=False)

    deliveries: Mapped[list["OrderEmailDelivery"]] = relationship(back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("order_id", "document_version", name="uq_order_documents_order_version"),
        CheckConstraint("content_length > 0", name="ck_order_documents_nonempty"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_order_documents_sha256"),
        Index("ix_order_documents_order_id", "order_id"),
    )


class OrderEmailDelivery(Base, TimestampMixin):
    __tablename__ = "order_email_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_documents.id", ondelete="CASCADE"), nullable=False)
    recipient_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", server_default="pending")
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[OrderDocument] = relationship(back_populates="deliveries")

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_order_email_delivery_idempotency"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{value}'" for value in DELIVERY_STATUSES) + ")",
            name="ck_order_email_delivery_status",
        ),
        CheckConstraint("batch_number >= 1", name="ck_order_email_delivery_batch"),
        CheckConstraint("attempts >= 0", name="ck_order_email_delivery_attempts"),
        Index("ix_order_email_deliveries_order_id", "order_id", "created_at"),
        Index("ix_order_email_deliveries_due", "next_attempt_at", "created_at", postgresql_where=text("status IN ('pending', 'processing')")),
        Index("ix_order_email_deliveries_provider_id", "provider_message_id", postgresql_where=text("provider_message_id IS NOT NULL")),
    )


class ResendWebhookEvent(Base):
    __tablename__ = "resend_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_resend_webhook_events_received_at", "received_at"),)
