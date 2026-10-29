"""E-mail do PDF do pedido: documento, entregas e eventos Resend.

Revision ID: order_email_r31
Revises: rug_pieces_r30
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "order_email_r31"
down_revision = "rug_pieces_r30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_email_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="ck_order_email_document_status"),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "version", name="uq_order_email_documents_order_version"),
    )
    op.create_index("ix_order_email_documents_due", "order_email_documents", ["status", "next_attempt_at", "created_at"])

    op.create_table(
        "order_email_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("resend_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_type", sa.String(length=80), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("origin IN ('finalization', 'manual_resend')", name="ck_order_email_delivery_origin"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'accepted', 'delivered', 'failed', 'needs_review', 'blocked', 'skipped')", name="ck_order_email_delivery_status"),
        sa.ForeignKeyConstraint(["document_id"], ["order_email_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resend_of_id"], ["order_email_deliveries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("provider_message_id"),
    )
    op.create_index("ix_order_email_deliveries_due", "order_email_deliveries", ["status", "next_attempt_at", "created_at"])
    op.create_index("ix_order_email_deliveries_order_created", "order_email_deliveries", ["order_id", "created_at", "id"])
    op.create_index(
        "uq_order_email_finalization_recipient",
        "order_email_deliveries",
        ["document_id", sa.text("lower(recipient_email)")],
        unique=True,
        postgresql_where=sa.text("origin = 'finalization' AND recipient_email IS NOT NULL AND recipient_email <> ''"),
    )

    op.create_table(
        "order_email_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("svix_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["order_email_deliveries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("svix_id"),
    )
    op.create_index("ix_order_email_webhook_message", "order_email_webhook_events", ["provider_message_id", "applied_at"])


def downgrade():
    op.drop_index("ix_order_email_webhook_message", table_name="order_email_webhook_events")
    op.drop_table("order_email_webhook_events")
    op.drop_index("uq_order_email_finalization_recipient", table_name="order_email_deliveries")
    op.drop_index("ix_order_email_deliveries_order_created", table_name="order_email_deliveries")
    op.drop_index("ix_order_email_deliveries_due", table_name="order_email_deliveries")
    op.drop_table("order_email_deliveries")
    op.drop_index("ix_order_email_documents_due", table_name="order_email_documents")
    op.drop_table("order_email_documents")
