"""Comentário por item do pedido

Cada item do pedido ganha `comment`, texto livre que o usuário escreve sobre
aquele item. É diferente de `observacao`, que é o snapshot da observação do
produto, e da opção "Customizado" dos opcionais. Itens existentes ficam vazios.

Revision ID: order_item_comment_r27
Revises: optional_custom_r26
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "order_item_comment_r27"
down_revision = "optional_custom_r26"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_items", sa.Column("comment", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("order_items", "comment")
