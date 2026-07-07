"""add products.price column (legacy field — also missing on Railway's DB)

Mesma causa raiz da migration 0024: o modelo sempre teve `price`, e a
migration 0003_add_product_price.py existe no historico, mas a coluna
nao existe no banco da Railway (confirmado via consulta direta a
information_schema.columns). IF NOT EXISTS torna a migration idempotente
e segura em qualquer ambiente.
"""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.drop_column('products', 'price')
