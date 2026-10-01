"""RBAC R2b: invariantes de mercado e capacidades de plataforma

Revision ID: rbac_r2b_20261001c
Revises: rbac_r2a_20261001b
Create Date: 2026-10-01

Impede que um vínculo de usuário BR aponte para cliente/representante EU (ou o
inverso) e limita capacidades de plataforma ao vocabulário implementado.
"""
from alembic import op


revision = "rbac_r2b_20261001c"
down_revision = "rbac_r2a_20261001b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_clients_id_market", "clients", ["id", "market_code"])
    op.create_unique_constraint(
        "uq_representatives_id_market", "representatives", ["id", "market_code"]
    )
    op.drop_constraint(
        "fk_user_markets_linked_client_id", "user_markets", type_="foreignkey"
    )
    op.drop_constraint("fk_user_markets_rep_id", "user_markets", type_="foreignkey")
    op.create_foreign_key(
        "fk_user_markets_client_same_market",
        "user_markets",
        "clients",
        ["linked_client_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_markets_rep_same_market",
        "user_markets",
        "representatives",
        ["rep_id", "market_code"],
        ["id", "market_code"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_user_platform_permissions_capability",
        "user_platform_permissions",
        "capability IN ('platform_admin', 'activate_market', 'read_outbox')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_platform_permissions_capability",
        "user_platform_permissions",
        type_="check",
    )
    op.drop_constraint(
        "fk_user_markets_rep_same_market", "user_markets", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_user_markets_client_same_market", "user_markets", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_user_markets_linked_client_id",
        "user_markets",
        "clients",
        ["linked_client_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_markets_rep_id",
        "user_markets",
        "representatives",
        ["rep_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_representatives_id_market", "representatives", type_="unique")
    op.drop_constraint("uq_clients_id_market", "clients", type_="unique")
