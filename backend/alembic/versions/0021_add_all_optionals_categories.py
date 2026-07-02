"""add all_optionals_categories to products"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('all_optionals_categories', sa.Text(), nullable=True, server_default=''))


def downgrade() -> None:
    op.drop_column('products', 'all_optionals_categories')
