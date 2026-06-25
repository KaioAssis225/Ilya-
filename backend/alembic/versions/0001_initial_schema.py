"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'products',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('product_code', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('altura', sa.Numeric(10, 2), nullable=False),
        sa.Column('largura', sa.Numeric(10, 2), nullable=False),
        sa.Column('profundidade', sa.Numeric(10, 2), nullable=False),
        sa.Column('opt_aluminio', sa.String(50), nullable=True),
        sa.Column('opt_tecido', sa.String(50), nullable=True),
        sa.Column('opt_corda', sa.String(50), nullable=True),
        sa.Column('photo_path', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_code'),
    )
    op.create_index('ix_products_product_code', 'products', ['product_code'])

    op.create_table(
        'clients',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('cep', sa.String(20), nullable=False),
        sa.Column('numero', sa.String(50), nullable=True),
        sa.Column('address', sa.String(255), nullable=False),
        sa.Column('city', sa.String(255), nullable=False),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'representatives',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('cep', sa.String(20), nullable=False),
        sa.Column('numero', sa.String(50), nullable=True),
        sa.Column('address', sa.String(255), nullable=False),
        sa.Column('city', sa.String(255), nullable=False),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'orders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('orc_id', sa.String(50), nullable=False),
        sa.Column('client_id', sa.Uuid(), nullable=False),
        sa.Column('rep_id', sa.Uuid(), nullable=True),
        sa.Column('total_value', sa.Numeric(12, 2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id']),
        sa.ForeignKeyConstraint(['rep_id'], ['representatives.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('orc_id'),
    )
    op.create_index('ix_orders_code', 'orders', ['code'])
    op.create_index('ix_orders_orc_id', 'orders', ['orc_id'])

    op.create_table(
        'order_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('product_code', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('altura', sa.Numeric(10, 2), nullable=False),
        sa.Column('largura', sa.Numeric(10, 2), nullable=False),
        sa.Column('profundidade', sa.Numeric(10, 2), nullable=False),
        sa.Column('opt_aluminio', sa.String(50), nullable=True),
        sa.Column('opt_tecido', sa.String(50), nullable=True),
        sa.Column('opt_corda', sa.String(50), nullable=True),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('order_items')
    op.drop_index('ix_orders_orc_id', 'orders')
    op.drop_index('ix_orders_code', 'orders')
    op.drop_table('orders')
    op.drop_table('representatives')
    op.drop_table('clients')
    op.drop_index('ix_products_product_code', 'products')
    op.drop_table('products')
