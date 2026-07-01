"""add product sets (is_set flag + product_set_items table)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('is_set', sa.Boolean(), nullable=False, server_default='false'))
    op.create_table(
        'product_set_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('set_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id'), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('ix_product_set_items_set_id', 'product_set_items', ['set_id'])


def downgrade() -> None:
    op.drop_index('ix_product_set_items_set_id', table_name='product_set_items')
    op.drop_table('product_set_items')
    op.drop_column('products', 'is_set')
