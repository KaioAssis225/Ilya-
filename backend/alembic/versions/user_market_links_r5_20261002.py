"""R5: um vínculo comercial por entidade em cada mercado

Revision ID: user_market_links_r5_20261002
Revises: products_market_r4_20261001
Create Date: 2026-10-02

Impede duas identidades de representarem o mesmo cliente ou representante no
mesmo mercado. A mesma identidade comercial pode continuar existindo de forma
independente em BR e EU.
"""
from alembic import op
import sqlalchemy as sa


revision = "user_market_links_r5_20261002"
down_revision = "products_market_r4_20261001"
branch_labels = None
depends_on = None


def _reject_duplicate_links(column: str) -> None:
    duplicate = op.get_bind().execute(sa.text(
        f"SELECT market_code, {column} FROM user_markets "
        f"WHERE {column} IS NOT NULL GROUP BY market_code, {column} "
        "HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            f"Migration R5 bloqueada: vínculo duplicado em user_markets.{column} "
            f"para o mercado {duplicate.market_code}."
        )


def upgrade() -> None:
    _reject_duplicate_links("linked_client_id")
    _reject_duplicate_links("rep_id")
    op.create_index(
        "uq_user_markets_client_per_market",
        "user_markets",
        ["market_code", "linked_client_id"],
        unique=True,
        postgresql_where=sa.text("linked_client_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_markets_rep_per_market",
        "user_markets",
        ["market_code", "rep_id"],
        unique=True,
        postgresql_where=sa.text("rep_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_markets_rep_per_market", table_name="user_markets")
    op.drop_index("uq_user_markets_client_per_market", table_name="user_markets")
