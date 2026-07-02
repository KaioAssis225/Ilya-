"""add observacao to products and order_items

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('observacao', sa.Text(), nullable=True))
    op.add_column('order_items', sa.Column('observacao', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('order_items', 'observacao')
    op.drop_column('products', 'observacao')
