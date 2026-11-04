"""Campos informativos do cadastro de clientes em Portugal.

Revision ID: eu_client_registration_r35
Revises: order_stage_r34
Create Date: 2026-11-04
"""

from alembic import op
import sqlalchemy as sa


revision = "eu_client_registration_r35"
down_revision = "order_stage_r34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("contact_name", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("client_type", sa.String(length=20), nullable=True))
    op.add_column("clients", sa.Column("observation", sa.String(length=2000), nullable=True))
    op.create_check_constraint(
        "ck_clients_client_type",
        "clients",
        "client_type IS NULL OR client_type IN ('lojista', 'corporativo', 'pvp', 'arquiteto')",
    )
    # Preserva a classificação que já era exibida no cadastro EU, mas a nova
    # coluna passa a ser independente das regras de preço a partir daqui.
    op.execute(
        "UPDATE clients SET client_type = price_profile "
        "WHERE market_code = 'EU' AND client_type IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_clients_client_type", "clients", type_="check")
    op.drop_column("clients", "observation")
    op.drop_column("clients", "client_type")
    op.drop_column("clients", "contact_name")
