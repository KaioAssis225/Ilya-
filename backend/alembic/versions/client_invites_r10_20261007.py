"""Convites de acesso e revogação das senhas iniciais de clientes legados.

Revision ID: client_invites_r10_20261007
Revises: fiscal_audit_r9_20261007
"""

import sqlalchemy as sa
from alembic import op


revision = "client_invites_r10_20261007"
down_revision = "fiscal_audit_r9_20261007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("client_access_requested_by_user_id", sa.Uuid(), nullable=True))
    op.create_table(
        "client_access_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("issued_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("verification_method", sa.String(length=30), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.CheckConstraint(
            "verification_method IN ('phone_callback', 'existing_contract', 'in_person')",
            name="ck_client_access_invitation_verification_method",
        ),
    )
    op.create_index(
        "ix_client_access_invitation_user_created", "client_access_invitations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_client_access_invitation_client_created", "client_access_invitations",
        ["client_id", "created_at"],
    )

    # A senha inicial foi mostrada ao criador da conta. As contas que ainda
    # exigem a primeira troca ficam inativas até o titular usar um convite.
    op.execute("""
        UPDATE refresh_tokens
        SET revoked = TRUE, revoked_at = now()
        WHERE revoked = FALSE AND user_id IN (
            SELECT u.id FROM users u
            WHERE u.must_change_password = TRUE
              AND (u.role = 'cliente' OR (u.role = 'vendedor' AND u.linked_id IS NOT NULL)
                   OR EXISTS (
                       SELECT 1 FROM user_markets um
                       WHERE um.user_id = u.id AND um.role = 'cliente'
                         AND um.linked_client_id IS NOT NULL
                   ))
        )
    """)
    op.execute("""
        UPDATE users u
        SET is_active = FALSE,
            hashed_password = 'revoked-client-setup:' || u.id::text,
            auth_version = u.auth_version + 1
        WHERE u.must_change_password = TRUE
          AND (u.role = 'cliente' OR (u.role = 'vendedor' AND u.linked_id IS NOT NULL)
               OR EXISTS (
                   SELECT 1 FROM user_markets um
                   WHERE um.user_id = u.id AND um.role = 'cliente'
                     AND um.linked_client_id IS NOT NULL
               ))
    """)


def downgrade() -> None:
    # Senhas iniciais conhecidas por terceiros não são restauradas.
    op.drop_index("ix_client_access_invitation_client_created", table_name="client_access_invitations")
    op.drop_index("ix_client_access_invitation_user_created", table_name="client_access_invitations")
    op.drop_table("client_access_invitations")
    op.drop_column("users", "client_access_requested_by_user_id")
