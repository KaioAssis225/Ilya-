"""add partial index for unread notifications

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


PARTIAL_INDEX_NAME = "ix_notifications_unread_user_created"
TABLE_NAME = "notifications"


def _drop_invalid_index(name: str) -> None:
    if op.get_context().as_sql:
        return

    invalid = op.get_bind().execute(
        sa.text(
            """
            SELECT NOT index_data.indisvalid
            FROM pg_index AS index_data
            JOIN pg_class AS index_class
              ON index_class.oid = index_data.indexrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = index_class.relnamespace
            WHERE index_class.relname = :name
              AND namespace.nspname = current_schema()
            """
        ),
        {"name": name},
    ).scalar()
    if invalid:
        op.drop_index(
            name,
            table_name=TABLE_NAME,
            if_exists=True,
            postgresql_concurrently=True,
        )


def upgrade() -> None:
    # A criação concorrente evita bloquear escritas na tabela durante o deploy.
    # Se um deploy anterior foi interrompido, remove primeiro o índice inválido.
    with op.get_context().autocommit_block():
        _drop_invalid_index(PARTIAL_INDEX_NAME)
        op.create_index(
            PARTIAL_INDEX_NAME,
            TABLE_NAME,
            ["user_id", "created_at"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
            postgresql_where=sa.text("is_read IS FALSE"),
        )
        op.execute("ANALYZE notifications")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            PARTIAL_INDEX_NAME,
            table_name=TABLE_NAME,
            if_exists=True,
            postgresql_concurrently=True,
        )
