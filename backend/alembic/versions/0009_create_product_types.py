"""create product_types table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
import uuid

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_types',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('name', sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('product_types')
