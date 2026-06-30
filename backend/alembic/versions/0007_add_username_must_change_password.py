"""add username, must_change_password, linked_id to users

Revision ID: 0007
Revises: 24635a791bff
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '24635a791bff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('linked_id', sa.Uuid(), nullable=True))
    op.create_unique_constraint('uq_users_username', 'users', ['username'])
    op.create_index('ix_users_username', 'users', ['username'])


def downgrade() -> None:
    op.drop_index('ix_users_username', 'users')
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'linked_id')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'username')
