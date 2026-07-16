"""add executivo role and can_view_dashboard flag (Bloco 95)

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'executivo'")

    op.add_column(
        "users",
        sa.Column("can_view_dashboard", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "can_view_dashboard")
    # PostgreSQL não suporta remover valores de enum — 'executivo' permanece no tipo, sem uso.
