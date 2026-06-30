"""add cadastros and produtos to userrole enum

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-30
"""
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'cadastros'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'produtos'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op
    pass
