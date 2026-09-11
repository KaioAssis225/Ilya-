"""adiciona acessos independentes por aplicacao ao usuario

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("has_ilya_access", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("has_stock_access", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "has_stock_access")
    op.drop_column("users", "has_ilya_access")
