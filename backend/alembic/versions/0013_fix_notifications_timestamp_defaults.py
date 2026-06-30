"""fix notifications timestamp server defaults
Revision ID: 0013
Revises: 0012
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'notifications', 'created_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()'),
        existing_nullable=False,
    )
    op.alter_column(
        'notifications', 'updated_at',
        existing_type=sa.DateTime(),
        server_default=sa.text('now()'),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'notifications', 'updated_at',
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        'notifications', 'created_at',
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )
