"""Peças de tapete (área total = largura × profundidade × peças)

A linha de tapete passa a aceitar várias peças com a mesma medida. A
quantidade cobrada em ``qty`` continua sendo o total em m², então pedidos
antigos seguem intactos.

Revision ID: rug_pieces_r30
Revises: rug_dimensions_r29
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa


revision = "rug_pieces_r30"
down_revision = "rug_dimensions_r29"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_items", sa.Column("area_pieces", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint(
        "ck_order_items_area_pieces_positive",
        "order_items",
        "area_pieces >= 1",
    )


def downgrade():
    op.drop_constraint("ck_order_items_area_pieces_positive", "order_items", type_="check")
    op.drop_column("order_items", "area_pieces")
