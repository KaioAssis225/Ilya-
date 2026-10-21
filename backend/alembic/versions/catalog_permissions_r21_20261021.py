"""R21: permissões de catálogo por representante/cliente e catálogo no pedido

Revision ID: catalog_permissions_r21
Revises: remove_order_signatures_r20
Create Date: 2026-10-21

Planejamento "Orçamentos, Catálogos e Permissões Comerciais" v1.2.0:

- DEC-01: `all_catalogs` em representatives e clients nasce `true`, então
  nenhum cadastro existente perde acesso no deploy. As tabelas de junção só
  valem quando a flag está desligada.
- DEC-02: `products.catalog_id` vira obrigatório e a FK deixa de anular o
  catálogo ao excluí-lo (RESTRICT). A rota de exclusão já responde 409.
- DEC-06: todo pedido passa a ter um catálogo. Os existentes são classificados
  pelo catálogo dos produtos dos itens; não há caminho de legado no código.

A revisão é abortiva, como market_fk_r7: produto sem catálogo ou pedido que não
se classifica em exatamente um catálogo interrompe o deploy listando os códigos,
em vez de deixar a integridade pela metade.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "catalog_permissions_r21"
down_revision = "remove_order_signatures_r20"
branch_labels = None
depends_on = None


_SAMPLE = 20

# Códigos de produto/pedido não são dados pessoais.
_PRODUCTS_WITHOUT_CATALOG = """
    SELECT market_code || ':' || product_code FROM products
    WHERE catalog_id IS NULL
    ORDER BY market_code, product_code
"""

_UNCLASSIFIABLE_ORDERS = """
    SELECT o.market_code || ':' || o.code FROM orders o
    LEFT JOIN order_items i ON i.order_id = o.id
    LEFT JOIN products p
      ON p.market_code = o.market_code AND p.product_code = i.product_code
    GROUP BY o.id, o.market_code, o.code
    HAVING count(i.id) = 0
        OR bool_or(p.id IS NULL)
        OR count(DISTINCT p.catalog_id) <> 1
    ORDER BY o.market_code, o.code
"""


def _offenders(sql: str) -> list[str]:
    return list(op.get_bind().exec_driver_sql(sql).scalars().all())


def _assert_classifiable() -> None:
    problems = []
    products = _offenders(_PRODUCTS_WITHOUT_CATALOG)
    if products:
        problems.append(
            f"{len(products)} produto(s) sem catálogo — atribua um catálogo ou "
            f"exclua: {', '.join(products[:_SAMPLE])}"
        )
    orders = _offenders(_UNCLASSIFIABLE_ORDERS)
    if orders:
        problems.append(
            f"{len(orders)} pedido(s) sem exatamente um catálogo (misturam "
            "catálogos, não têm itens ou têm item de produto inexistente) — "
            f"separe em um pedido por catálogo ou cancele: {', '.join(orders[:_SAMPLE])}"
        )
    if problems:
        raise RuntimeError(
            "Migration abortada — corrija os registros antes do deploy:\n  - "
            + "\n  - ".join(problems)
        )


def _junction(table: str, owner_column: str, owner_table: str) -> None:
    op.create_table(
        table,
        sa.Column(owner_column, UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        # A FK composta impede vincular catálogo de outro mercado.
        sa.ForeignKeyConstraint(
            [owner_column, "market_code"],
            [f"{owner_table}.id", f"{owner_table}.market_code"],
            name=f"fk_{table}_owner_same_market",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_id", "market_code"],
            ["catalogs.id", "catalogs.market_code"],
            name=f"fk_{table}_catalog_same_market",
            ondelete="CASCADE",
        ),
    )
    op.create_index(f"ix_{table}_catalog_id", table, ["catalog_id"])


def upgrade() -> None:
    _assert_classifiable()

    # DEC-02: catálogo obrigatório e não mais anulado pela exclusão.
    op.drop_constraint(
        "fk_products_catalog_same_market", "products", type_="foreignkey"
    )
    op.alter_column("products", "catalog_id", nullable=False)
    op.create_foreign_key(
        "fk_products_catalog_same_market",
        "products",
        "catalogs",
        ["catalog_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )

    # DEC-01: todos começam liberados.
    for table in ("representatives", "clients"):
        op.add_column(
            table,
            sa.Column(
                "all_catalogs",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    _junction("representative_catalogs", "representative_id", "representatives")
    _junction("client_catalogs", "client_id", "clients")

    # DEC-06: catálogo do pedido, preenchido pelos itens.
    op.add_column("orders", sa.Column("catalog_id", UUID(as_uuid=True), nullable=True))
    op.add_column("orders", sa.Column("catalog_name", sa.String(length=50), nullable=True))
    op.execute(
        """
        UPDATE orders o
        SET catalog_id = c.id, catalog_name = c.name
        FROM order_items i
        JOIN products p ON p.product_code = i.product_code
        JOIN catalogs c ON c.id = p.catalog_id
        WHERE i.order_id = o.id AND p.market_code = o.market_code
        """
    )
    op.alter_column("orders", "catalog_id", nullable=False)
    op.alter_column("orders", "catalog_name", nullable=False)
    op.create_foreign_key(
        "fk_orders_catalog_same_market",
        "orders",
        "catalogs",
        ["catalog_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_orders_catalog_id", "orders", ["catalog_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_catalog_id", table_name="orders")
    op.drop_constraint("fk_orders_catalog_same_market", "orders", type_="foreignkey")
    op.drop_column("orders", "catalog_name")
    op.drop_column("orders", "catalog_id")

    op.drop_table("client_catalogs")
    op.drop_table("representative_catalogs")
    op.drop_column("clients", "all_catalogs")
    op.drop_column("representatives", "all_catalogs")

    op.drop_constraint(
        "fk_products_catalog_same_market", "products", type_="foreignkey"
    )
    op.alter_column("products", "catalog_id", nullable=True)
    op.execute(
        """
        ALTER TABLE products
        ADD CONSTRAINT fk_products_catalog_same_market
        FOREIGN KEY (catalog_id, market_code)
        REFERENCES catalogs (id, market_code)
        ON DELETE SET NULL (catalog_id)
        """
    )
