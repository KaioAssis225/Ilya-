"""add order_seq sequence for atomic order code generation

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-30
"""
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Inicializa a sequência a partir do maior número já usado nos pedidos
    # para não colidir com códigos existentes (ex: PED-0042 → começa em 43)
    op.execute("""
        DO $$
        DECLARE
            next_val INTEGER;
        BEGIN
            SELECT COALESCE(
                MAX(CAST(SUBSTRING(code FROM 5) AS INTEGER)), 0
            ) + 1 INTO next_val FROM orders;
            EXECUTE 'CREATE SEQUENCE IF NOT EXISTS order_seq START WITH ' || next_val;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS order_seq")
