"""source_version and is_active for cross-database reads (Ilya Estoque appendix)

Migration/01-PLANO-SOURCE-VERSION-E-SOFT-DELETE.md — decisão ratificada em
05/08/2026 (Migration/02-DECISOES-CONFIRMADAS-ALTO-COMANDO-2026-08-05.md).

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "products",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "orders",
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("orders", "source_version")
    op.drop_column("products", "is_active")
    op.drop_column("products", "source_version")
