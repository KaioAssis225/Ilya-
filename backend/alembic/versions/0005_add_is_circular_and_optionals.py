"""add is_circular, optionals catalog, drop price and opt columns from products

Revision ID: 0005
Revises: 0003
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── optionals catalog table ──────────────────────────────────────────────
    op.create_table(
        'optionals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('color_name', sa.String(100), nullable=False),
        sa.Column('photo_path', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ── product_optionals N-to-N ─────────────────────────────────────────────
    op.create_table(
        'product_optionals',
        sa.Column('product_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('optional_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('optionals.id', ondelete='CASCADE'), primary_key=True),
    )

    # ── products: drop obsolete columns, add is_circular ────────────────────
    op.drop_column('products', 'price')
    op.drop_column('products', 'opt_aluminio')
    op.drop_column('products', 'opt_tecido')
    op.drop_column('products', 'opt_corda')
    op.add_column('products', sa.Column('is_circular', sa.Boolean(), nullable=False, server_default='false'))

    # ── order_items: add is_circular snapshot ────────────────────────────────
    op.add_column('order_items', sa.Column('is_circular', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('order_items', 'is_circular')
    op.drop_column('products', 'is_circular')
    op.add_column('products', sa.Column('opt_corda', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('opt_tecido', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('opt_aluminio', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('price', sa.Numeric(10, 2), nullable=False, server_default='0'))
    op.drop_table('product_optionals')
    op.drop_table('optionals')
