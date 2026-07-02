"""add order history and finalization fields"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'order_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_history_order_id', 'order_history', ['order_id'])

    op.add_column('orders', sa.Column('is_finalized', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('orders', sa.Column('external_code', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'external_code')
    op.drop_column('orders', 'is_finalized')
    op.drop_index('ix_order_history_order_id', table_name='order_history')
    op.drop_table('order_history')
