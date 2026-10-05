"""R7: integridade de mercado no banco (Bloco 05, item 5)

Revision ID: market_fk_r7_20261005
Revises: catalog_dimensions_r6_20261002
Create Date: 2026-10-05

Até aqui o cruzamento entre mercados era barrado apenas na aplicação (o listener
de `db/market_scope.py` e as validações das rotas). As FKs eram simples, então o
banco aceitaria um pedido EU apontando para cliente BR. Esta revisão move a
invariante para o schema, como o Checkpoint 05 exige ("banco rejeita pedido PT
com cliente/representante BR").

Relações convertidas em FK composta `(id, market_code)`:

- `orders` -> `clients`, com RESTRICT: pedido nunca perde o cliente.
- `orders` -> `representatives`, com `SET NULL (rep_id)`: o vínculo é anulável,
  mas `market_code` é NOT NULL. Um `ON DELETE SET NULL` sem lista de colunas
  anula **todas** as colunas da FK e a remoção do representante falharia com
  "null value in column market_code violates not-null constraint" — verificado
  em PostgreSQL 16.14. A forma com coluna explícita (PG 15+) anula só `rep_id`.
- `products` -> `catalogs`, com `SET NULL (catalog_id)`: mesma razão.

`product_types` -> `product_groups` **não** entra: `product_groups` é entidade
global, sem `market_code` (carrega `ipi`, conceito brasileiro). A decisão está
registrada em `registros/05-isolamento-inventario-20261005.md`, seção 5, para o
Bloco 06.

O Alembic 1.18 não expõe a lista de colunas do SET NULL em `create_foreign_key`
(a assinatura só aceita `ondelete` como texto), então essas duas constraints são
criadas por `op.execute` com DDL explícito.

A revisão é abortiva: havendo linha cruzada, falha nomeando a relação em vez de
deixar a integridade pela metade.
"""
from alembic import op


revision = "market_fk_r7_20261005"
down_revision = "catalog_dimensions_r6_20261002"
branch_labels = None
depends_on = None


# (rótulo legível, SQL de contagem) — somente agregados, nenhum dado pessoal.
_CROSS_CHECKS = (
    (
        "orders.client_id aponta para cliente de outro mercado",
        """
        SELECT count(*) FROM orders o
        JOIN clients c ON c.id = o.client_id
        WHERE c.market_code <> o.market_code
        """,
    ),
    (
        "orders.rep_id aponta para representante de outro mercado",
        """
        SELECT count(*) FROM orders o
        JOIN representatives r ON r.id = o.rep_id
        WHERE o.rep_id IS NOT NULL AND r.market_code <> o.market_code
        """,
    ),
    (
        "products.catalog_id aponta para catálogo de outro mercado",
        """
        SELECT count(*) FROM products p
        JOIN catalogs c ON c.id = p.catalog_id
        WHERE p.catalog_id IS NOT NULL AND c.market_code <> p.market_code
        """,
    ),
)


def _assert_no_cross_market_rows() -> None:
    conn = op.get_bind()
    offenders = []
    for label, sql in _CROSS_CHECKS:
        count = conn.exec_driver_sql(sql).scalar() or 0
        if count:
            offenders.append(f"{count} linha(s): {label}")
    if offenders:
        raise RuntimeError(
            "Migration abortada — há dados cruzados entre mercados. "
            "Reclassifique os registros antes de aplicar a integridade:\n  - "
            + "\n  - ".join(offenders)
        )


def upgrade() -> None:
    _assert_no_cross_market_rows()

    # Alvo da FK composta. clients e representatives ganharam o seu em
    # rbac_r2b_20261001c; catalogs ainda não tinha.
    op.create_unique_constraint(
        "uq_catalogs_id_market", "catalogs", ["id", "market_code"]
    )

    # orders -> clients: pedido não perde o cliente.
    op.drop_constraint("orders_client_id_fkey", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_client_same_market",
        "orders",
        "clients",
        ["client_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )

    # orders -> representatives: anula apenas rep_id, preservando market_code.
    op.drop_constraint("orders_rep_id_fkey", "orders", type_="foreignkey")
    op.execute(
        """
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_rep_same_market
        FOREIGN KEY (rep_id, market_code)
        REFERENCES representatives (id, market_code)
        ON DELETE SET NULL (rep_id)
        """
    )

    # products -> catalogs: dimensão opcional, anula apenas catalog_id.
    op.drop_constraint("fk_products_catalog_id", "products", type_="foreignkey")
    op.execute(
        """
        ALTER TABLE products
        ADD CONSTRAINT fk_products_catalog_same_market
        FOREIGN KEY (catalog_id, market_code)
        REFERENCES catalogs (id, market_code)
        ON DELETE SET NULL (catalog_id)
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_products_catalog_same_market", "products", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_products_catalog_id", "products", "catalogs", ["catalog_id"], ["id"]
    )

    op.drop_constraint("fk_orders_rep_same_market", "orders", type_="foreignkey")
    op.create_foreign_key(
        "orders_rep_id_fkey", "orders", "representatives", ["rep_id"], ["id"]
    )

    op.drop_constraint("fk_orders_client_same_market", "orders", type_="foreignkey")
    op.create_foreign_key(
        "orders_client_id_fkey", "orders", "clients", ["client_id"], ["id"]
    )

    op.drop_constraint("uq_catalogs_id_market", "catalogs", type_="unique")
