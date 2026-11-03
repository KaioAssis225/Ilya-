"""Etapa do pedido finalizado: Produção → Entregue

Revision ID: order_stage_r34
Revises: eu_subgroups_br_r33
Create Date: 2026-11-03
"""

from alembic import op
import sqlalchemy as sa


revision = "order_stage_r34"
down_revision = "eu_subgroups_br_r33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("order_stage", sa.String(length=20), nullable=True))
    op.add_column("orders", sa.Column("production_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        "UPDATE orders SET order_stage = 'production', production_started_at = finalized_at "
        "WHERE is_finalized AND NOT is_cancelled"
    )

    op.create_check_constraint(
        "ck_orders_stage_valid",
        "orders",
        "order_stage IS NULL OR order_stage IN ('production', 'delivered')",
    )
    op.create_check_constraint(
        "ck_orders_stage_requires_finalized",
        "orders",
        "order_stage IS NULL OR is_finalized",
    )
    op.create_check_constraint(
        "ck_orders_stage_delivered_at",
        "orders",
        "(order_stage = 'delivered' AND delivered_at IS NOT NULL) OR (order_stage IS DISTINCT FROM 'delivered' AND delivered_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_stage_delivered_at", "orders", type_="check")
    op.drop_constraint("ck_orders_stage_requires_finalized", "orders", type_="check")
    op.drop_constraint("ck_orders_stage_valid", "orders", type_="check")

    op.drop_column("orders", "delivered_at")
    op.drop_column("orders", "production_started_at")
    op.drop_column("orders", "order_stage")
