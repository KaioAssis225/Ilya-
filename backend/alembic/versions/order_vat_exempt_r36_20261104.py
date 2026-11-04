"""Orçamento EU sem IVA: flag e código do motivo de isenção.

Revision ID: order_vat_exempt_r36
Revises: eu_client_registration_r35
Create Date: 2026-11-04

Aditiva: pedidos existentes ficam com vat_exempt = false e sem motivo.
"""

from alembic import op
import sqlalchemy as sa


revision = "order_vat_exempt_r36"
down_revision = "eu_client_registration_r35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("vat_exempt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("orders", sa.Column("vat_exemption_code", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_orders_vat_exemption_consistent",
        "orders",
        "(vat_exempt AND vat_exemption_code IS NOT NULL AND market_code = 'EU') "
        "OR (NOT vat_exempt AND vat_exemption_code IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_vat_exemption_consistent", "orders", type_="check")
    op.drop_column("orders", "vat_exemption_code")
    op.drop_column("orders", "vat_exempt")
