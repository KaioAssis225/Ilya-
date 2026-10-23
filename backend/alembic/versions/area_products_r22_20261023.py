"""Adiciona suporte a vendas de tapetes por metro quadrado

Cria colunas em produtos para limite de área, altera a quantidade de itens de pedido para aceitar até 2 casas decimais, e adiciona flag indicando venda por área. No downgrade, as casas decimais são perdidas (arredondamento para inteiro) e as colunas de área são removidas.

Revision ID: area_products_r22
Revises: catalog_permissions_r21
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa


revision = "area_products_r22"
down_revision = "catalog_permissions_r21"
branch_labels = None
depends_on = None


def upgrade():
    # Adiciona colunas para controle de limite de área em produtos
    op.add_column(
        "products",
        sa.Column(
            "area_limit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("products", sa.Column("max_area_m2", sa.Numeric(10, 2), nullable=True))

    # Cria restrição: se o limite estiver ativo, max_area_m2 deve ser positivo
    op.create_check_constraint(
        "ck_products_area_limit_requires_max",
        "products",
        "NOT area_limit_enabled OR (max_area_m2 IS NOT NULL AND max_area_m2 > 0)",
    )

    # Altera quantidade em itens de pedido para suportar 2 casas decimais
    op.alter_column(
        "order_items",
        "qty",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        existing_nullable=False,
        postgresql_using="qty::numeric(10,2)",
    )

    # Adiciona flag de venda por área em itens de pedido
    op.add_column(
        "order_items",
        sa.Column(
            "sold_by_area",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Backfill: marca como vendidos por área os itens cujo produto é tapete
    op.execute(
        """
        UPDATE order_items AS i
        SET sold_by_area = true
        FROM orders AS o, products AS p, catalogs AS c
        WHERE i.order_id = o.id
          AND i.product_code = p.product_code
          AND p.market_code = o.market_code
          AND p.catalog_id = c.id
          AND lower(trim(c.name)) IN ('tapete', 'tapetes')
        """
    )


def downgrade():
    # Remove flag de venda por área
    op.drop_column("order_items", "sold_by_area")

    # Reverte quantidade para inteiro (arredondando)
    op.alter_column(
        "order_items",
        "qty",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
        postgresql_using="round(qty)::integer",
    )

    # Remove restrição e colunas de área em produtos
    op.drop_constraint(
        "ck_products_area_limit_requires_max",
        "products",
        type_="check",
    )
    op.drop_column("products", "max_area_m2")
    op.drop_column("products", "area_limit_enabled")
