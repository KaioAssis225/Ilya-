"""add canonical lifecycle timestamps for LGPD retention

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE clients "
        "SET last_activity_at = COALESCE(updated_at, created_at, now())"
    )
    op.alter_column("clients", "last_activity_at", nullable=False)
    op.drop_index("ix_clients_retention_updated_id", table_name="clients")
    op.create_index(
        "ix_clients_retention_activity_id",
        "clients",
        ["last_activity_at", "id"],
    )

    op.add_column(
        "representatives",
        sa.Column(
            "relationship_ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_representatives_retention_end_id",
        "representatives",
        ["relationship_ended_at", "id"],
        postgresql_where=sa.text("relationship_ended_at IS NOT NULL"),
    )

    op.add_column(
        "orders",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE orders SET finalized_at = COALESCE(updated_at, created_at) "
        "WHERE is_finalized = true"
    )
    op.execute(
        "UPDATE orders SET cancelled_at = COALESCE(updated_at, created_at) "
        "WHERE is_cancelled = true"
    )
    op.create_check_constraint(
        "ck_orders_finalized_timestamp",
        "orders",
        "is_finalized = (finalized_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_orders_cancelled_timestamp",
        "orders",
        "is_cancelled = (cancelled_at IS NOT NULL)",
    )
    op.drop_index(
        "ix_orders_retention_closed_updated_id",
        table_name="orders",
    )
    op.create_index(
        "ix_orders_retention_finalized_at_id",
        "orders",
        ["finalized_at", "id"],
        postgresql_where=sa.text("is_finalized = true"),
    )
    op.create_index(
        "ix_orders_retention_cancelled_at_id",
        "orders",
        ["cancelled_at", "id"],
        postgresql_where=sa.text("is_cancelled = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orders_retention_cancelled_at_id",
        table_name="orders",
    )
    op.drop_index(
        "ix_orders_retention_finalized_at_id",
        table_name="orders",
    )
    op.create_index(
        "ix_orders_retention_closed_updated_id",
        "orders",
        ["updated_at", "id"],
        postgresql_where=sa.text(
            "is_finalized = true OR is_cancelled = true"
        ),
    )
    op.drop_constraint(
        "ck_orders_cancelled_timestamp",
        "orders",
        type_="check",
    )
    op.drop_constraint(
        "ck_orders_finalized_timestamp",
        "orders",
        type_="check",
    )
    op.drop_column("orders", "cancelled_at")
    op.drop_column("orders", "finalized_at")

    op.drop_index(
        "ix_representatives_retention_end_id",
        table_name="representatives",
    )
    op.drop_column("representatives", "relationship_ended_at")

    op.drop_index(
        "ix_clients_retention_activity_id",
        table_name="clients",
    )
    op.create_index(
        "ix_clients_retention_updated_id",
        "clients",
        ["updated_at", "id"],
    )
    op.drop_column("clients", "last_activity_at")
