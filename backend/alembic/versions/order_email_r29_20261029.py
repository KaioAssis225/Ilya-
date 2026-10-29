"""Documentos imutáveis e entregas de pedidos por e-mail.

Revision ID: order_email_r29
Revises: admin_order_rep_r28
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa


revision = "order_email_r29"
down_revision = "admin_order_rep_r28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_length", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("content_length > 0", name="ck_order_documents_nonempty"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_order_documents_sha256"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "document_version", name="uq_order_documents_order_version"),
    )
    op.create_index("ix_order_documents_order_id", "order_documents", ["order_id"])
    op.create_table(
        "order_email_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("recipient_kind", sa.String(length=40), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("batch_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('missing_address', 'pending', 'processing', 'accepted', 'sent', 'delivered', 'delayed', 'failed', 'bounced', 'complained', 'suppressed')", name="ck_order_email_delivery_status"),
        sa.CheckConstraint("batch_number >= 1", name="ck_order_email_delivery_batch"),
        sa.CheckConstraint("attempts >= 0", name="ck_order_email_delivery_attempts"),
        sa.ForeignKeyConstraint(["document_id"], ["order_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_order_email_delivery_idempotency"),
    )
    op.create_index("ix_order_email_deliveries_order_id", "order_email_deliveries", ["order_id", "created_at"])
    op.create_index("ix_order_email_deliveries_due", "order_email_deliveries", ["next_attempt_at", "created_at"], postgresql_where=sa.text("status IN ('pending', 'processing')"))
    op.create_index("ix_order_email_deliveries_provider_id", "order_email_deliveries", ["provider_message_id"], postgresql_where=sa.text("provider_message_id IS NOT NULL"))
    op.create_table(
        "resend_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_resend_webhook_events_received_at", "resend_webhook_events", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_resend_webhook_events_received_at", table_name="resend_webhook_events")
    op.drop_table("resend_webhook_events")
    op.drop_index("ix_order_email_deliveries_provider_id", table_name="order_email_deliveries")
    op.drop_index("ix_order_email_deliveries_due", table_name="order_email_deliveries")
    op.drop_index("ix_order_email_deliveries_order_id", table_name="order_email_deliveries")
    op.drop_table("order_email_deliveries")
    op.drop_index("ix_order_documents_order_id", table_name="order_documents")
    op.drop_table("order_documents")
