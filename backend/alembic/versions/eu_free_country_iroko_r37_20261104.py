"""Allow free country text in EU records and move two Iroko finishes to IBTW.

Revision ID: eu_free_country_iroko_r37
Revises: order_vat_exempt_r36
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op


revision = "eu_free_country_iroko_r37"
down_revision = "order_vat_exempt_r36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("clients", "representatives"):
        op.alter_column(
            table,
            "country",
            existing_type=sa.String(length=2),
            type_=sa.String(length=120),
            existing_nullable=False,
        )

    op.execute(
        """
        UPDATE optionals
           SET brand = 'IBTW'
         WHERE market_code = 'EU'
           AND category = 'MADEIRA'
           AND color_name IN ('IROKO CARVÃO ÓLEO', 'IROKO PATINA ÓLEO')
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    too_long = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1 FROM clients WHERE length(country) > 2
                UNION ALL
                SELECT 1 FROM representatives WHERE length(country) > 2
            )
            """
        )
    ).scalar_one()
    if too_long:
        raise RuntimeError(
            "Downgrade bloqueado: existem países com mais de duas letras; "
            "reduzi-los apagaria informação cadastrada."
        )

    op.execute(
        """
        UPDATE optionals
           SET brand = 'ILYA'
         WHERE market_code = 'EU'
           AND category = 'MADEIRA'
           AND color_name IN ('IROKO CARVÃO ÓLEO', 'IROKO PATINA ÓLEO')
        """
    )

    for table in ("clients", "representatives"):
        op.alter_column(
            table,
            "country",
            existing_type=sa.String(length=120),
            type_=sa.String(length=2),
            existing_nullable=False,
        )
