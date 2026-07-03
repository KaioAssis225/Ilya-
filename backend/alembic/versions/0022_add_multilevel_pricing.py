"""add multilevel pricing (price_lojista/price_corporativo + client price_profile)"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('price_lojista', sa.Numeric(10, 2), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('price_corporativo', sa.Numeric(10, 2), nullable=False, server_default='0'))
    # Backfill: preços novos herdam o preço legado existente (no-op se não houver linhas)
    op.execute("UPDATE products SET price_lojista = price, price_corporativo = price")
    op.add_column('clients', sa.Column('price_profile', sa.String(20), nullable=False, server_default='lojista'))


def downgrade() -> None:
    op.drop_column('clients', 'price_profile')
    op.drop_column('products', 'price_corporativo')
    op.drop_column('products', 'price_lojista')
