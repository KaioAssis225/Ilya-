"""add product price

Revision ID: 3c5013d00082
Revises: 0006
Create Date: 2026-06-26 17:21:16.188999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c5013d00082'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('products', 'price')
