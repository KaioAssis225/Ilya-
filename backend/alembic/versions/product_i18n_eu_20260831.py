"""Add localized Portugal product names.

Revision ID: product_i18n_eu_20260831
Revises: europa_multimarket_20260820
"""

from alembic import op
import sqlalchemy as sa


revision = "product_i18n_eu_20260831"
down_revision = "europa_multimarket_20260820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_markets", sa.Column("description_pt_pt", sa.Text(), nullable=True))
    op.add_column("product_markets", sa.Column("description_en", sa.Text(), nullable=True))

    # A primeira carga preserva nomes próprios/modelos e adapta somente os
    # termos comerciais inequivocamente diferentes. Depois, ambos os nomes
    # permanecem editáveis no cadastro Portugal e na importação europeia.
    op.execute("""
        UPDATE product_markets pm
        SET description_pt_pt = trim(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(p.description, '\\mBANQUETA\\M', 'BANCO ALTO', 'gi'),
                        '\\mPOLTRONA\\M', 'CADEIRÃO', 'gi'
                    ),
                    '\\mC/ BCS\\M', 'COM BRAÇOS', 'gi'
                )
            )
        FROM products p
        WHERE pm.product_id = p.id AND pm.market_code = 'EU'
    """)
    op.execute("""
        UPDATE product_markets
        SET description_pt_pt = regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(description_pt_pt, 'S/ *BCS', 'SEM BRAÇOS', 'gi'),
                    'C/ *BCS', 'COM BRAÇOS', 'gi'
                ),
                '\\mMESA JANTAR\\M', 'MESA DE JANTAR', 'gi'
            ),
            '\\mMESA CENTRO\\M', 'MESA DE CENTRO', 'gi'
        )
        WHERE market_code = 'EU'
    """)
    op.execute("""
        UPDATE product_markets
        SET description_pt_pt = regexp_replace(
            regexp_replace(description_pt_pt, '\\mLUMINÁRIA DE CHÃO\\M', 'CANDEEIRO DE PÉ', 'gi'),
            '\\mLUMINÁRIA\\M', 'CANDEEIRO', 'gi'
        )
        WHERE market_code = 'EU'
    """)

    op.execute("""
        UPDATE product_markets pm
        SET description_en = trim(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                p.description,
                '\\mMESA DE JANTAR\\M', 'DINING TABLE', 'gi'),
                '\\mMESA DE CENTRO\\M', 'COFFEE TABLE', 'gi'),
                '\\mMESA LATERAL\\M', 'SIDE TABLE', 'gi'),
                '\\mLUMINÁRIA DE CHÃO\\M', 'FLOOR LAMP', 'gi'),
                '\\mLUMINÁRIA DE MESA\\M', 'TABLE LAMP', 'gi'),
                '\\mESPREGUIÇADEIRA\\M', 'SUN LOUNGER', 'gi'),
                '\\mBANQUETA\\M', 'BAR STOOL', 'gi'),
                '\\mPOLTRONA\\M', 'ARMCHAIR', 'gi'),
                '\\mCADEIRA\\M', 'CHAIR', 'gi'),
                '\\mAPARADOR\\M', 'CONSOLE TABLE', 'gi'),
                '\\mSOFÁ\\M', 'SOFA', 'gi'),
                '\\mCONJUNTO\\M', 'SET', 'gi')
            )
        FROM products p
        WHERE pm.product_id = p.id AND pm.market_code = 'EU'
    """)
    op.execute("""
        UPDATE product_markets
        SET description_en = regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                description_en,
                'C/ *BCS', 'WITH ARMS', 'gi'),
                'S/ *BCS', 'WITHOUT ARMS', 'gi'),
                '\\mMESA JANTAR\\M', 'DINING TABLE', 'gi'),
                '\\mMESA CENTRO\\M', 'COFFEE TABLE', 'gi'),
                '\\mCOM BRAÇOS\\M', 'WITH ARMS', 'gi'),
                '\\mSEM BRAÇOS\\M', 'WITHOUT ARMS', 'gi'),
                '\\mCOM FURO\\M', 'WITH PARASOL HOLE', 'gi'),
                '\\mSEM FURO\\M', 'WITHOUT PARASOL HOLE', 'gi')
        WHERE market_code = 'EU'
    """)
    # Características mantêm a mesma ordem do nome BR, mas deixam de ficar
    # parcialmente em português no título inglês.
    op.execute("""
        UPDATE product_markets
        SET description_en = regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
            regexp_replace(regexp_replace(regexp_replace(regexp_replace(
                description_en,
                '\\mRETANGULAR\\M', 'RECTANGULAR', 'gi'),
                '\\mQUADRADA?\\M', 'SQUARE', 'gi'),
                '\\mREDONDA?\\M', 'ROUND', 'gi'),
                '\\mSEM FURO\\M', 'WITHOUT PARASOL HOLE', 'gi'),
                '\\mCOM FURO\\M', 'WITH PARASOL HOLE', 'gi'),
                '\\mMADEIRA\\M', 'WOOD', 'gi'),
                '\\mALUMÍNIO\\M', 'ALUMINIUM', 'gi'),
                '\\mCORDA\\M', 'ROPE', 'gi'),
                '\\mTECIDO\\M', 'FABRIC', 'gi'),
                '\\mVIDRO\\M', 'GLASS', 'gi'),
                '\\mAÇO\\M', 'STEEL', 'gi'),
                '\\mTAMPO\\M', 'TOP', 'gi')
        WHERE market_code = 'EU'
    """)


def downgrade() -> None:
    op.drop_column("product_markets", "description_en")
    op.drop_column("product_markets", "description_pt_pt")
