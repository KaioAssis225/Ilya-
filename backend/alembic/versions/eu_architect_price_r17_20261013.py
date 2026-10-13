"""Adiciona a lista Arquiteto exclusivamente ao mercado EU.

Revision ID: eu_architect_price_r17
Revises: moloni_article_metadata_r16
"""

import uuid

import sqlalchemy as sa
from alembic import op


revision = "eu_architect_price_r17"
down_revision = "moloni_article_metadata_r16"
branch_labels = None
depends_on = None

_EU_ARCHITECT_ID = uuid.UUID("e1000000-0000-0000-0000-000000000004")


def upgrade() -> None:
    price_lists = sa.table(
        "price_lists",
        sa.column("id", sa.Uuid()),
        sa.column("market_code", sa.String(2)),
        sa.column("code", sa.String(30)),
        sa.column("name", sa.String(100)),
        sa.column("currency", sa.String(3)),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        price_lists,
        [
            {
                "id": _EU_ARCHITECT_ID,
                "market_code": "EU",
                "code": "arquiteto",
                "name": "Arquiteto",
                "currency": "EUR",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM price_lists "
            "WHERE id = CAST(:price_list_id AS uuid) "
            "AND market_code = 'EU' AND code = 'arquiteto'"
        ).bindparams(price_list_id=_EU_ARCHITECT_ID)
    )
