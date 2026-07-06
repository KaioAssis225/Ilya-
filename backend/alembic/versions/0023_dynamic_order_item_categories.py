"""replace fixed opt_* columns with dynamic opt_categories JSON on order_items"""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('order_items', sa.Column('opt_categories', sa.JSON(), nullable=False, server_default='{}'))
    op.drop_column('order_items', 'opt_aluminio')
    op.drop_column('order_items', 'opt_madeira')
    op.drop_column('order_items', 'opt_tecido')
    op.drop_column('order_items', 'opt_couro')
    op.drop_column('order_items', 'opt_corda')


def downgrade() -> None:
    op.add_column('order_items', sa.Column('opt_aluminio', sa.String(100), nullable=True))
    op.add_column('order_items', sa.Column('opt_madeira', sa.String(100), nullable=True))
    op.add_column('order_items', sa.Column('opt_tecido', sa.String(100), nullable=True))
    op.add_column('order_items', sa.Column('opt_couro', sa.String(100), nullable=True))
    op.add_column('order_items', sa.Column('opt_corda', sa.String(100), nullable=True))
    op.drop_column('order_items', 'opt_categories')
