"""Traduz nomes em português dos 14 produtos EU cadastrados em inglês.

Revision ID: eu_product_names_pt_r32
Revises: order_email_r31
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa


revision = "eu_product_names_pt_r32"
down_revision = "order_email_r31"
branch_labels = None
depends_on = None


EU_PRODUCT_PT_TRANSLATIONS = [
    ("MC0378", "1960 - MESA DE CENTRO RETANGULAR - 1,20 X 1,04 - PEDRA SINTERIZADA"),
    ("MC0379", "1960 - MESA DE CENTRO REDONDA - Ø 1,24 - PEDRA SINTERIZADA"),
    ("ML0257", "1960 - MESA LATERAL REDONDA - Ø 0,44 - PEDRA SINTERIZADA"),
    ("ML0258", "1960 - MESA LATERAL REDONDA - Ø 0,54 - PEDRA SINTERIZADA"),
    ("ML0259", "1960 - MESA LATERAL QUADRADA - 0,50 X 0,54 - PEDRA SINTERIZADA"),
    ("MJ0528", "LUDO - MESA DE JANTAR REDONDA - Ø 1,60 - MÁRMORE"),
    ("MJ0529", "LUDO - MESA DE JANTAR REDONDA - Ø 1,60 - PEDRA SINTERIZADA"),
    ("MB0027", "MORE - MESA BISTRÔ REDONDA - Ø 1,20 - PEDRA SINTERIZADA"),
    ("MC0380", "NATURAL - ALTA MESA DE CENTRO QUADRADA - 1,00 X 1,00 - PEDRA SINTERIZADA"),
    ("MC0381", "NATURAL - MÉDIA MESA DE CENTRO QUADRADA - 1,00 X 1,00 - PEDRA SINTERIZADA"),
    ("MC0382", "ONE - MESA DE CENTRO REDONDA - Ø 0,80 - PEDRA SINTERIZADA"),
    ("MC0383", "ONE - MESA DE CENTRO REDONDA - Ø 0,80 - PEDRA SINTERIZADA"),
    ("MC0384", "ONE - MESA DE CENTRO REDONDA - Ø 1,20 - PEDRA SINTERIZADA"),
    ("CD0033", "SAMUI - CADEIRA DE JANTAR"),
]


def upgrade() -> None:
    bind = op.get_bind()
    update_products = sa.text("""
        UPDATE products
        SET description = :pt_desc,
            source_version = COALESCE(source_version, 1) + 1
        WHERE market_code = 'EU'
          AND product_code = :code
    """)
    update_product_markets = sa.text("""
        UPDATE product_markets pm
        SET description_pt_pt = :pt_desc,
            updated_at = now()
        FROM products p
        WHERE pm.product_id = p.id
          AND pm.market_code = 'EU'
          AND p.market_code = 'EU'
          AND p.product_code = :code
    """)
    for code, pt_desc in EU_PRODUCT_PT_TRANSLATIONS:
        bind.execute(update_products, {"code": code, "pt_desc": pt_desc})
        bind.execute(update_product_markets, {"code": code, "pt_desc": pt_desc})


def downgrade() -> None:
    pass
