"""Normalize the agreed English term for products with arms.

Revision ID: product_i18n_eu_arms_20260831
Revises: product_i18n_eu_terms_20260831
"""

from alembic import op


revision = "product_i18n_eu_arms_20260831"
down_revision = "product_i18n_eu_terms_20260831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE product_markets
        SET description_en = regexp_replace(
            regexp_replace(description_en, '\\mWITH ARMS\\M', 'WITH ARMS', 'gi'),
            '\\mCOM BRAÇOS\\M', 'WITH ARMS', 'gi'
        )
        WHERE market_code = 'EU'
    """)


def downgrade() -> None:
    # The localized display value is intentionally not rewritten backwards;
    # the source Brazilian title remains the canonical fallback.
    pass
