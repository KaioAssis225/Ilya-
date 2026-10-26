"""Pedido pode misturar catálogos

`orders.catalog_id` e `orders.catalog_name` passam a aceitar NULL: ficam
preenchidos quando todos os itens são de um só catálogo e vazios quando o
pedido mistura catálogos. A permissão continua valendo para cada catálogo dos
itens (validada na rota). Sem backfill: pedidos existentes já têm um catálogo.

Revision ID: order_multi_catalog_r24
Revises: price_list_access_r23
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


revision = "order_multi_catalog_r24"
down_revision = "price_list_access_r23"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("orders", "catalog_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("orders", "catalog_name", existing_type=sa.String(50), nullable=True)


def downgrade():
    # Pedido misto volta a ter um catálogo só: o do primeiro item (por código).
    op.execute(
        """
        UPDATE orders o
        SET catalog_id = first_item.catalog_id, catalog_name = first_item.catalog_name
        FROM (
            SELECT DISTINCT ON (oi.order_id)
                oi.order_id, p.catalog_id, c.name AS catalog_name
            FROM order_items oi
            JOIN orders o2 ON o2.id = oi.order_id
            JOIN products p
              ON p.product_code = oi.product_code AND p.market_code = o2.market_code
            JOIN catalogs c ON c.id = p.catalog_id
            ORDER BY oi.order_id, oi.product_code
        ) AS first_item
        WHERE o.id = first_item.order_id AND o.catalog_id IS NULL
        """
    )
    op.alter_column("orders", "catalog_name", existing_type=sa.String(50), nullable=False)
    op.alter_column("orders", "catalog_id", existing_type=sa.Uuid(), nullable=False)
