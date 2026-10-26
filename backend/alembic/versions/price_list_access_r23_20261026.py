"""Permissões de tabela de preço por representante e cliente

Adiciona `all_price_lists` e `price_list_codes` em representantes e clientes.
Representante nasce com todas as tabelas liberadas (comportamento atual);
cliente nasce com `false` e lista vazia, que significa apenas o perfil de
faturamento do próprio cadastro — também o comportamento atual do portal.
Assim não é necessário backfill.

Revision ID: price_list_access_r23
Revises: area_products_r22
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "price_list_access_r23"
down_revision = "area_products_r22"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "representatives",
        sa.Column(
            "all_price_lists",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "representatives",
        sa.Column(
            "price_list_codes",
            postgresql.ARRAY(sa.String(30)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "all_price_lists",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "price_list_codes",
            postgresql.ARRAY(sa.String(30)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade():
    op.drop_column("clients", "price_list_codes")
    op.drop_column("clients", "all_price_lists")
    op.drop_column("representatives", "price_list_codes")
    op.drop_column("representatives", "all_price_lists")
