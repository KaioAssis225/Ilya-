"""corrige o login do representante FLP

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-10
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

OLD_USERNAME = "flprepresetacoes"
NEW_USERNAME = "flprepresentacoes"


def upgrade() -> None:
    if not context.is_offline_mode():
        existing_target = op.get_bind().execute(
            sa.text("SELECT 1 FROM users WHERE username = :username LIMIT 1"),
            {"username": NEW_USERNAME},
        ).scalar_one_or_none()
        if existing_target:
            raise RuntimeError(
                f"Não foi possível corrigir {OLD_USERNAME}: {NEW_USERNAME} já existe."
            )

    op.execute(
        sa.text(
            """
            UPDATE users
               SET username = :new_username,
                   auth_version = auth_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = :old_username
            """
        ).bindparams(old_username=OLD_USERNAME, new_username=NEW_USERNAME)
    )

    op.execute(
        sa.text(
            """
            UPDATE refresh_tokens
               SET revoked = TRUE,
                   revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP)
             WHERE user_id IN (
                 SELECT id FROM users WHERE username = :new_username
             )
               AND revoked = FALSE
            """
        ).bindparams(new_username=NEW_USERNAME)
    )


def downgrade() -> None:
    if not context.is_offline_mode():
        existing_old = op.get_bind().execute(
            sa.text("SELECT 1 FROM users WHERE username = :username LIMIT 1"),
            {"username": OLD_USERNAME},
        ).scalar_one_or_none()
        if existing_old:
            raise RuntimeError(
                f"Não foi possível restaurar {OLD_USERNAME}: o login já existe."
            )

    op.execute(
        sa.text(
            """
            UPDATE users
               SET username = :old_username,
                   auth_version = auth_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = :new_username
            """
        ).bindparams(old_username=OLD_USERNAME, new_username=NEW_USERNAME)
    )
