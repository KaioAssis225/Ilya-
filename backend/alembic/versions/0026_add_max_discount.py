"""add max_discount to clients and representatives (Bloco 69)

Controle dinamico de desconto maximo: cada cliente e representante tem seu
proprio teto de desconto por item, em vez do limite fixo por role.
"""
from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS max_discount NUMERIC(5, 2) NOT NULL DEFAULT 0.00"
    )
    op.execute(
        "ALTER TABLE representatives ADD COLUMN IF NOT EXISTS max_discount NUMERIC(5, 2) NOT NULL DEFAULT 15.00"
    )


def downgrade() -> None:
    op.drop_column('clients', 'max_discount')
    op.drop_column('representatives', 'max_discount')
