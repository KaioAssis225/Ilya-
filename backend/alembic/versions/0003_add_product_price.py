"""add price to products

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('price', sa.Numeric(10, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('products', 'price')
