"""classifica IBQ0014 e IBQ0015 como banquetas

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-11

Os produtos tinham descrições de banqueta, mas estavam gravados com o tipo
``Outro``. Por isso apareciam na busca textual e eram corretamente excluídos
quando o catálogo filtrava o subgrupo ``Banqueta``.
"""
from alembic import op
import sqlalchemy as sa


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_PRODUCT_CODES = ("IBQ0014", "IBQ0015")


def _set_product_type(product_type: str) -> None:
    bind = op.get_bind()
    placeholders = ", ".join(f":code_{index}" for index in range(len(_PRODUCT_CODES)))
    parameters = {
        **{f"code_{index}": code for index, code in enumerate(_PRODUCT_CODES)},
        "product_type": product_type,
    }
    bind.execute(
        sa.text(
            f"""
        UPDATE products
           SET type = :product_type,
               source_version = source_version + 1,
               updated_at = CURRENT_TIMESTAMP
         WHERE product_code IN ({placeholders})
        """
        ),
        parameters,
    )


def upgrade() -> None:
    _set_product_type("Banqueta")


def downgrade() -> None:
    _set_product_type("Outro")
