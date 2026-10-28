"""Dimensões do tapete (largura × profundidade)

Pedidos de tapete passam a informar as medidas em metros; o servidor calcula a
área cobrada. Itens antigos continuam sem as dimensões, e só os dois campos
juntos são aceitos.

Revision ID: rug_dimensions_r29
Revises: admin_order_rep_r28
Create Date: 2026-10-28
"""
from alembic import op
import sqlalchemy as sa


revision = "rug_dimensions_r29"
down_revision = "admin_order_rep_r28"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_items", sa.Column("area_width_m", sa.Numeric(10, 3), nullable=True))
    op.add_column("order_items", sa.Column("area_depth_m", sa.Numeric(10, 3), nullable=True))
    op.create_check_constraint(
        "ck_order_items_area_dims_pair",
        "order_items",
        "(area_width_m IS NULL AND area_depth_m IS NULL) OR (area_width_m > 0 AND area_depth_m > 0)",
    )


def downgrade():
    op.drop_constraint("ck_order_items_area_dims_pair", "order_items", type_="check")
    op.drop_column("order_items", "area_depth_m")
    op.drop_column("order_items", "area_width_m")
