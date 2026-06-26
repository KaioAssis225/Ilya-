"""add opt_madeira and opt_couro to order_items

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("opt_madeira", sa.String(100), nullable=True))
    op.add_column("order_items", sa.Column("opt_couro", sa.String(100), nullable=True))
    # Widen existing columns to accommodate "category/color" qualified format
    op.alter_column("order_items", "opt_tecido", type_=sa.String(100), existing_nullable=True)
    op.alter_column("order_items", "opt_aluminio", type_=sa.String(100), existing_nullable=True)
    op.alter_column("order_items", "opt_corda", type_=sa.String(100), existing_nullable=True)


def downgrade() -> None:
    op.drop_column("order_items", "opt_madeira")
    op.drop_column("order_items", "opt_couro")
    op.alter_column("order_items", "opt_tecido", type_=sa.String(50), existing_nullable=True)
    op.alter_column("order_items", "opt_aluminio", type_=sa.String(50), existing_nullable=True)
    op.alter_column("order_items", "opt_corda", type_=sa.String(50), existing_nullable=True)
