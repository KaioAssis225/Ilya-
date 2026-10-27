"""Representante fixo de pedidos para administradores

Revision ID: admin_order_rep_r28
Revises: order_item_comment_r27
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "admin_order_rep_r28"
down_revision = "order_item_comment_r27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_markets",
        sa.Column("order_rep_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_markets_order_rep_same_market",
        "user_markets",
        "representatives",
        ["order_rep_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_user_markets_order_rep_admin",
        "user_markets",
        "order_rep_id IS NULL OR role = 'admin'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_markets_order_rep_admin", "user_markets", type_="check"
    )
    op.drop_constraint(
        "fk_user_markets_order_rep_same_market", "user_markets", type_="foreignkey"
    )
    op.drop_column("user_markets", "order_rep_id")
