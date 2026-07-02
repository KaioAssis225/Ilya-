"""add discount to order_items"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'order_items',
        sa.Column('discount', sa.Numeric(5, 2), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('order_items', 'discount')
