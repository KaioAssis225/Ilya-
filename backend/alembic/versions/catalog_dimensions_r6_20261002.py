"""R6: dimensões do catálogo independentes por mercado

Revision ID: catalog_dimensions_r6_20261002
Revises: user_market_links_r5_20261002
Create Date: 2026-10-02

Os registros existentes sustentam o catálogo-base confirmado como BR e são
classificados como BR. Nenhuma dimensão ou vínculo EU é criado automaticamente;
o catálogo português será cadastrado manualmente.
"""
from alembic import op
import sqlalchemy as sa


revision = "catalog_dimensions_r6_20261002"
down_revision = "user_market_links_r5_20261002"
branch_labels = None
depends_on = None


_TABLES = ("catalogs", "product_types", "optional_categories", "optionals")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("market_code", sa.String(2), nullable=True, server_default="BR"),
        )
        op.execute(sa.text(f"UPDATE {table} SET market_code = 'BR' WHERE market_code IS NULL"))
        op.alter_column(
            table,
            "market_code",
            existing_type=sa.String(2),
            nullable=False,
            server_default="BR",
        )
        op.create_foreign_key(
            f"fk_{table}_market_code", table, "markets", ["market_code"], ["code"]
        )

    op.drop_constraint("catalogs_name_key", "catalogs", type_="unique")
    op.create_unique_constraint("uq_catalogs_market_name", "catalogs", ["market_code", "name"])
    op.drop_constraint("product_types_name_key", "product_types", type_="unique")
    op.create_unique_constraint(
        "uq_product_types_market_name", "product_types", ["market_code", "name"]
    )
    op.drop_constraint("optional_categories_code_key", "optional_categories", type_="unique")
    op.create_unique_constraint(
        "uq_optional_categories_market_code",
        "optional_categories",
        ["market_code", "code"],
    )
    op.create_index(
        "ix_optionals_market_category_id",
        "optionals",
        ["market_code", "category", "id"],
    )


def downgrade() -> None:
    for table, column in (
        ("catalogs", "name"),
        ("product_types", "name"),
        ("optional_categories", "code"),
    ):
        duplicate = op.get_bind().execute(sa.text(
            f"SELECT {column} FROM {table} GROUP BY {column} HAVING count(*) > 1 LIMIT 1"
        )).first()
        if duplicate:
            raise RuntimeError(
                f"Downgrade bloqueado: {table}.{column} se repete entre mercados."
            )

    op.drop_index("ix_optionals_market_category_id", table_name="optionals")
    op.drop_constraint("uq_optional_categories_market_code", "optional_categories", type_="unique")
    op.create_unique_constraint("optional_categories_code_key", "optional_categories", ["code"])
    op.drop_constraint("uq_product_types_market_name", "product_types", type_="unique")
    op.create_unique_constraint("product_types_name_key", "product_types", ["name"])
    op.drop_constraint("uq_catalogs_market_name", "catalogs", type_="unique")
    op.create_unique_constraint("catalogs_name_key", "catalogs", ["name"])
    for table in reversed(_TABLES):
        op.drop_constraint(f"fk_{table}_market_code", table, type_="foreignkey")
        op.drop_column(table, "market_code")
