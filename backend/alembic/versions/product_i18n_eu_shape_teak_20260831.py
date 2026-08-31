"""Normalize English EU product shape and teak terminology.

Revision ID: product_i18n_eu_shape_teak_20260831
Revises: product_i18n_eu_arms_20260831
"""

from alembic import op


revision = "product_i18n_eu_shape_teak_20260831"
down_revision = "product_i18n_eu_arms_20260831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Product names keep the Brazilian order/model code, while shape terms
    # are consistently localized for the English EU catalog. Teka is a wood
    # species/material name and is intentionally omitted from the English
    # display title rather than translated.
    op.execute(r"""
        UPDATE product_markets
        SET description_en = trim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(description_en,
                                    '\mREDONDO\M', 'ROUND', 'gi'),
                                '\mREDONDA\M', 'ROUND', 'gi'),
                            '\mRETANGULAR\M', 'RECTANGULAR', 'gi'),
                        '\mWITH[[:space:]]+TEAK\M', '', 'gi'),
                    '\mCOM[[:space:]]+TEKA\M', '', 'gi'),
                '\mTEKA\M', '', 'gi'),
            '[[:space:]]{2,}', ' ', 'g')
        )
        WHERE market_code = 'EU' AND description_en IS NOT NULL
    """)


def downgrade() -> None:
    # The English display value is derived from the Brazilian source title;
    # restoring removed material words would be ambiguous.
    pass
