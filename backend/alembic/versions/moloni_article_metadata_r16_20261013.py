"""Campos comerciais de artigo inspirados na exportação Moloni.

Revision ID: moloni_article_metadata_r16
Revises: moloni_company_id_bigint_r15
"""
import sqlalchemy as sa
from alembic import op

revision = "moloni_article_metadata_r16"
down_revision = "moloni_company_id_bigint_r15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("ean", sa.String(13), nullable=True))
    op.add_column("products", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("article_category_path", sa.String(255), nullable=True))
    op.create_index("ix_products_market_article_category", "products", ["market_code", "article_category_path"])


def downgrade() -> None:
    op.drop_index("ix_products_market_article_category", table_name="products")
    op.drop_column("products", "article_category_path")
    op.drop_column("products", "summary")
    op.drop_column("products", "ean")
