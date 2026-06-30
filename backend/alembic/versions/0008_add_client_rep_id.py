"""add rep_id to clients for ownership tracking

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('rep_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_clients_rep_id', 'clients', 'representatives',
        ['rep_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_clients_rep_id', 'clients', type_='foreignkey')
    op.drop_column('clients', 'rep_id')
