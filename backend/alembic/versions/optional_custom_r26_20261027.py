"""Opção "Customizado" em toda aplicação de opcional

Uma escolha customizada não aponta para um opcional do cadastro: guarda
`optional_name = 'Customizado'`, `optional_id` vazio e o texto digitado pelo
usuário em `custom_text`. Escolhas existentes ficam com o texto vazio.

Revision ID: optional_custom_r26
Revises: optional_brands_r25
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa


revision = "optional_custom_r26"
down_revision = "optional_brands_r25"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_item_optional_choices", sa.Column("custom_text", sa.Text(), nullable=True))


def downgrade():
    # A descrição sobrevive no nome da opção, cortada ao tamanho da coluna.
    op.execute(
        """
        UPDATE order_item_optional_choices
        SET optional_name = left(optional_name || ': ' || custom_text, 100)
        WHERE custom_text IS NOT NULL
        """
    )
    op.drop_column("order_item_optional_choices", "custom_text")
