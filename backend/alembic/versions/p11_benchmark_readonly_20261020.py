"""P11: papel técnico somente leitura para benchmark e sonda.

Revision ID: p11_benchmark_readonly
Revises: optional_applications_r18
"""

from alembic import op


revision = "p11_benchmark_readonly"
down_revision = "optional_applications_r18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'benchmark_readonly'")
    op.drop_constraint("ck_user_markets_role", "user_markets", type_="check")
    op.drop_constraint("ck_user_markets_role_links", "user_markets", type_="check")
    op.create_check_constraint(
        "ck_user_markets_role", "user_markets",
        "role IS NULL OR role IN ('admin', 'vendedor', 'representante', "
        "'cadastros', 'produtos', 'cliente', 'executivo', 'benchmark_readonly')",
    )
    op.create_check_constraint(
        "ck_user_markets_role_links", "user_markets",
        "(role IS NULL AND linked_client_id IS NULL AND rep_id IS NULL) OR "
        "(role = 'cliente' AND linked_client_id IS NOT NULL AND rep_id IS NULL) OR "
        "(role = 'representante' AND rep_id IS NOT NULL AND linked_client_id IS NULL) OR "
        "(role IN ('admin', 'vendedor', 'cadastros', 'produtos', 'executivo', "
        "'benchmark_readonly') AND linked_client_id IS NULL AND rep_id IS NULL)",
    )


def downgrade() -> None:
    # PostgreSQL não remove valores individuais de enum. A presença de uma
    # identidade técnica impede recuar as constraints até ela ser revogada.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM users WHERE role::text = 'benchmark_readonly')
             OR EXISTS (SELECT 1 FROM user_markets WHERE role = 'benchmark_readonly') THEN
            RAISE EXCEPTION 'Revogue identidades benchmark_readonly antes do downgrade';
          END IF;
        END $$
    """)
    op.drop_constraint("ck_user_markets_role", "user_markets", type_="check")
    op.drop_constraint("ck_user_markets_role_links", "user_markets", type_="check")
    op.create_check_constraint(
        "ck_user_markets_role", "user_markets",
        "role IS NULL OR role IN ('admin', 'vendedor', 'representante', "
        "'cadastros', 'produtos', 'cliente', 'executivo')",
    )
    op.create_check_constraint(
        "ck_user_markets_role_links", "user_markets",
        "(role IS NULL AND linked_client_id IS NULL AND rep_id IS NULL) OR "
        "(role = 'cliente' AND linked_client_id IS NOT NULL AND rep_id IS NULL) OR "
        "(role = 'representante' AND rep_id IS NOT NULL AND linked_client_id IS NULL) OR "
        "(role IN ('admin', 'vendedor', 'cadastros', 'produtos', 'executivo') "
        "AND linked_client_id IS NULL AND rep_id IS NULL)",
    )
