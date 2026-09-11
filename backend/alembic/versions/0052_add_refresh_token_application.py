"""identifica a aplicacao da sessao central

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "application",
            sa.String(length=20),
            nullable=False,
            server_default="ilya",
        ),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "application")
