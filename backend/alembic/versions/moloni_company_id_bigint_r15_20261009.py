"""Permite IDs reais de empresa Moloni acima de 32 bits.

Revision ID: moloni_company_id_bigint_r15
Revises: moloni_integration_r14_20261009
"""
import sqlalchemy as sa
from alembic import op

revision = "moloni_company_id_bigint_r15"
down_revision = "moloni_integration_r14_20261009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column("moloni_connections", "company_id", existing_type=sa.Integer(), type_=sa.BigInteger())
    op.alter_column("moloni_oauth_states", "company_id", existing_type=sa.Integer(), type_=sa.BigInteger())

def downgrade() -> None:
    op.alter_column("moloni_oauth_states", "company_id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.alter_column("moloni_connections", "company_id", existing_type=sa.BigInteger(), type_=sa.Integer())
