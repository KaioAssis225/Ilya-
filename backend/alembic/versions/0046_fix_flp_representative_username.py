"""corrige o login do representante FLP

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

OLD_USERNAME = "flprepresetacoes"
NEW_USERNAME = "flprepresentacoes"


def upgrade() -> None:
    connection = op.get_bind()
    existing_target = connection.execute(
        sa.text("SELECT 1 FROM users WHERE username = :username LIMIT 1"),
        {"username": NEW_USERNAME},
    ).scalar_one_or_none()
    if existing_target:
        raise RuntimeError(
            f"Não foi possível corrigir {OLD_USERNAME}: {NEW_USERNAME} já existe."
        )

    connection.execute(
        sa.text(
            """
            UPDATE users
               SET username = :new_username,
                   auth_version = auth_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = :old_username
            """
        ),
        {"old_username": OLD_USERNAME, "new_username": NEW_USERNAME},
    )

    connection.execute(
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
        ),
        {"new_username": NEW_USERNAME},
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing_old = connection.execute(
        sa.text("SELECT 1 FROM users WHERE username = :username LIMIT 1"),
        {"username": OLD_USERNAME},
    ).scalar_one_or_none()
    if existing_old:
        raise RuntimeError(
            f"Não foi possível restaurar {OLD_USERNAME}: o login já existe."
        )

    connection.execute(
        sa.text(
            """
            UPDATE users
               SET username = :old_username,
                   auth_version = auth_version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE username = :new_username
            """
        ),
        {"old_username": OLD_USERNAME, "new_username": NEW_USERNAME},
    )
