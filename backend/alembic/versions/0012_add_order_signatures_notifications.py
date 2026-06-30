"""add order signatures and notifications table
Revision ID: 0012
Revises: 0011
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('rep_signature', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('client_signature', sa.Text(), nullable=True))
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notifications_user_id', 'notifications')
    op.drop_table('notifications')
    op.drop_column('orders', 'client_signature')
    op.drop_column('orders', 'rep_signature')
