"""Correct agreed English furniture terminology for Portugal.

Revision ID: product_i18n_eu_terms_20260831
Revises: product_i18n_eu_20260831
"""

from alembic import op


revision = "product_i18n_eu_terms_20260831"
down_revision = "product_i18n_eu_20260831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the original BR word order/model identifiers; only replace the
    # approved English commercial terms in the localized EU title.
    op.execute("""
        UPDATE product_markets
        SET description_en = regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(description_en, '\\mBAR CART\\M', 'BAR TROLLEY', 'gi'),
                        '\\mCARRINHO BAR\\M', 'BAR TROLLEY', 'gi'
                    ),
                    '\\m(TABLE|FLOOR) LAMP\\M', 'FLOOR LAMP', 'gi'
                ),
                '\\mLAMP\\M', 'FLOOR LAMP', 'gi'
            ),
            '\\mSET\\M', 'FURNITURE SET', 'gi'
        )
        WHERE market_code = 'EU'
    """)
    op.execute("""
        UPDATE product_markets
        SET description_en = regexp_replace(description_en, '\\mPUFF\\M', 'POUF', 'gi')
        WHERE market_code = 'EU'
    """)


def downgrade() -> None:
    # These are display translations. Reversing them would be ambiguous
    # (e.g. a genuine model containing "SET"), so leave data untouched.
    pass
