"""add is_cancelled flag to orders (dashboard cancelled orders report)

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("orders", "is_cancelled")
