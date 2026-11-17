"""Renomeia a box inicial de showroom para Estoque Portugal.

Mantém tabelas e contratos internos para compatibilidade; altera somente o
nome padrão já apresentado aos usuários.
"""

from alembic import op
import sqlalchemy as sa


revision = "rename_showroom_stock_r48"
down_revision = "showroom_boxes_r47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE showroom_boxes SET name = 'Estoque Portugal', updated_at = now() "
        "WHERE market_code = 'EU' AND lower(name) = 'showroom portugal'"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE showroom_boxes SET name = 'Showroom Portugal', updated_at = now() "
        "WHERE market_code = 'EU' AND lower(name) = 'estoque portugal'"
    ))
