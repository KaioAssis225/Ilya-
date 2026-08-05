"""add canonical markers for auxiliary retention

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE notifications SET read_at = COALESCE(updated_at, created_at) "
        "WHERE is_read = true"
    )
    op.create_check_constraint(
        "ck_notifications_read_timestamp",
        "notifications",
        "is_read = (read_at IS NOT NULL)",
    )
    op.create_index(
        "ix_notifications_retention_read_id",
        "notifications",
        ["read_at", "id"],
        postgresql_where=sa.text("is_read IS TRUE"),
    )
    op.create_index(
        "ix_notifications_retention_unread_id",
        "notifications",
        ["created_at", "id"],
        postgresql_where=sa.text("is_read IS FALSE"),
    )

    op.add_column(
        "integration_outbox",
        sa.Column(
            "dead_lettered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE integration_outbox "
        "SET dead_lettered_at = COALESCE(updated_at, created_at) "
        "WHERE status = 'dead_letter'"
    )
    op.create_check_constraint(
        "ck_integration_outbox_dead_letter_timestamp",
        "integration_outbox",
        "(status = 'dead_letter') = (dead_lettered_at IS NOT NULL)",
    )
    op.create_index(
        "ix_integration_outbox_retention_delivered",
        "integration_outbox",
        ["delivered_at", "id"],
        postgresql_where=sa.text("status = 'delivered'"),
    )
    op.create_index(
        "ix_integration_outbox_dead_lettered",
        "integration_outbox",
        ["dead_lettered_at", "id"],
        postgresql_where=sa.text("status = 'dead_letter'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_outbox_dead_lettered",
        table_name="integration_outbox",
    )
    op.drop_index(
        "ix_integration_outbox_retention_delivered",
        table_name="integration_outbox",
    )
    op.drop_constraint(
        "ck_integration_outbox_dead_letter_timestamp",
        "integration_outbox",
        type_="check",
    )
    op.drop_column("integration_outbox", "dead_lettered_at")

    op.drop_index(
        "ix_notifications_retention_unread_id",
        table_name="notifications",
    )
    op.drop_index(
        "ix_notifications_retention_read_id",
        table_name="notifications",
    )
    op.drop_constraint(
        "ck_notifications_read_timestamp",
        "notifications",
        type_="check",
    )
    op.drop_column("notifications", "read_at")
