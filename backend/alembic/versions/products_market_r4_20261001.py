"""R4: produto independente por mercado, sem copiar inventário EU

Revision ID: products_market_r4_20261001
Revises: rbac_r2b_20261001c
Create Date: 2026-10-01

Todo produto legado é classificado como BR conforme confirmação do responsável.
Nenhum SKU EU é criado ou copiado: o catálogo europeu será cadastrado e revisto
manualmente depois. Vínculos ProductMarket/ProductPrice EU legados permanecem
como evidência, mas deixam de ser materializados pelas consultas operacionais,
pois Product passa a ser escopado pelo mercado ativo.
"""
from alembic import op
import sqlalchemy as sa


revision = "products_market_r4_20261001"
down_revision = "rbac_r2b_20261001c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("market_code", sa.String(2), nullable=True, server_default="BR"),
    )
    op.execute(sa.text("UPDATE products SET market_code = 'BR' WHERE market_code IS NULL"))
    op.alter_column(
        "products",
        "market_code",
        existing_type=sa.String(2),
        nullable=False,
        server_default="BR",
    )
    op.create_foreign_key(
        "fk_products_market_code", "products", "markets", ["market_code"], ["code"]
    )
    op.drop_constraint("products_product_code_key", "products", type_="unique")
    op.create_unique_constraint(
        "uq_products_market_code", "products", ["market_code", "product_code"]
    )
    op.create_index("ix_products_market_id", "products", ["market_code", "id"])


def downgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(
        "SELECT product_code FROM products GROUP BY product_code HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError(
            "Downgrade bloqueado: existem códigos de produto repetidos entre mercados."
        )
    op.drop_index("ix_products_market_id", table_name="products")
    op.drop_constraint("uq_products_market_code", "products", type_="unique")
    op.create_unique_constraint("products_product_code_key", "products", ["product_code"])
    op.drop_constraint("fk_products_market_code", "products", type_="foreignkey")
    op.drop_column("products", "market_code")
