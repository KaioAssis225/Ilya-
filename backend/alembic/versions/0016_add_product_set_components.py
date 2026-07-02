"""add product set components (free-form component modeling for Conjunto type)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_set_components',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('set_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('is_circular', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('altura', sa.Numeric(10, 2), nullable=False),
        sa.Column('largura', sa.Numeric(10, 2), nullable=False),
        sa.Column('profundidade', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('qty', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('ix_product_set_components_set_id', 'product_set_components', ['set_id'])
    op.create_table(
        'product_set_component_optionals',
        sa.Column('component_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('product_set_components.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('optional_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('optionals.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('product_set_component_optionals')
    op.drop_index('ix_product_set_components_set_id', table_name='product_set_components')
    op.drop_table('product_set_components')
