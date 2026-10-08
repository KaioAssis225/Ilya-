"""Substitui bloqueio global por contenção de login por origem e identificador.

Revision ID: login_protection_r12_20261007
Revises: signature_integrity_r11_20261007
"""

import sqlalchemy as sa
from alembic import op


revision = "login_protection_r12_20261007"
down_revision = "signature_integrity_r11_20261007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempt_states",
        sa.Column("identifier_fingerprint", sa.String(64), nullable=False),
        sa.Column("origin_fingerprint", sa.String(64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("identifier_fingerprint", "origin_fingerprint"),
    )
    op.create_index(
        "ix_login_attempt_states_last_failed_at", "login_attempt_states", ["last_failed_at"]
    )
    op.create_index(
        "ix_login_attempt_states_identifier", "login_attempt_states", ["identifier_fingerprint"]
    )
    # Remove bloqueios globais herdados. As colunas ficam por compatibilidade de
    # downgrade, mas deixam de participar da autenticação.
    op.execute("UPDATE users SET failed_login_attempts = 0, locked_until = NULL")


def downgrade() -> None:
    op.drop_index("ix_login_attempt_states_identifier", table_name="login_attempt_states")
    op.drop_index("ix_login_attempt_states_last_failed_at", table_name="login_attempt_states")
    op.drop_table("login_attempt_states")
