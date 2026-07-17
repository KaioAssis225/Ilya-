"""add deterministic directory sorting indexes

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_clients_name_id", "clients", ["name", "id"]),
    ("ix_clients_email_id", "clients", ["email", "id"]),
    ("ix_clients_phone_id", "clients", ["phone", "id"]),
    ("ix_clients_city_id", "clients", ["city", "id"]),
    (
        "ix_clients_max_discount_id",
        "clients",
        ["max_discount", "id"],
    ),
    (
        "ix_representatives_name_id",
        "representatives",
        ["name", "id"],
    ),
    (
        "ix_representatives_email_id",
        "representatives",
        ["email", "id"],
    ),
    (
        "ix_representatives_phone_id",
        "representatives",
        ["phone", "id"],
    ),
    (
        "ix_representatives_city_id",
        "representatives",
        ["city", "id"],
    ),
    (
        "ix_representatives_state_id",
        "representatives",
        ["state", "id"],
    ),
    (
        "ix_representatives_max_discount_id",
        "representatives",
        ["max_discount", "id"],
    ),
    ("ix_users_full_name_id", "users", ["full_name", "id"]),
    ("ix_products_type_id", "products", ["type", "id"]),
    (
        "ix_products_price_lojista_id",
        "products",
        ["price_lojista", "id"],
    ),
    (
        "ix_products_price_corporativo_id",
        "products",
        ["price_corporativo", "id"],
    ),
    (
        "ix_optionals_category_color_id",
        "optionals",
        ["category", "color_name", "id"],
    ),
)

EXPRESSION_INDEXES = (
    (
        "uq_clients_email_lower",
        "clients",
        "lower(email)",
        True,
    ),
    (
        "ix_representatives_name_lower_id",
        "representatives",
        "lower(name), id",
        False,
    ),
    (
        "uq_representatives_email_lower",
        "representatives",
        "lower(email)",
        True,
    ),
    (
        "uq_users_email_lower",
        "users",
        "lower(email)",
        True,
    ),
    (
        "ix_products_description_prefix_id",
        "products",
        "left(description, 512), id",
        False,
    ),
)

TRGM_INDEXES = (
    ("ix_clients_email_trgm", "clients", "email"),
    ("ix_clients_city_trgm", "clients", "city"),
    (
        "ix_representatives_email_trgm",
        "representatives",
        "email",
    ),
    (
        "ix_representatives_city_trgm",
        "representatives",
        "city",
    ),
    ("ix_users_full_name_trgm", "users", "full_name"),
    ("ix_users_email_trgm", "users", "email"),
    ("ix_users_username_trgm", "users", "username"),
)


def _drop_invalid_index(name: str, table_name: str) -> None:
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
            table_name=table_name,
            if_exists=True,
            postgresql_concurrently=True,
        )


def _create_expression_index(
    name: str,
    table_name: str,
    expression: str,
    unique: bool,
) -> None:
    _drop_invalid_index(name, table_name)
    unique_sql = "UNIQUE " if unique else ""
    op.execute(
        sa.text(
            f'CREATE {unique_sql}INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
            f'ON "{table_name}" ({expression})'
        )
    )


def _assert_normalized_emails_are_unique() -> None:
    if op.get_context().as_sql:
        return
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT source_table, normalized_email, quantity
            FROM (
                SELECT
                    'clients' AS source_table,
                    lower(email) AS normalized_email,
                    count(*) AS quantity
                FROM clients
                GROUP BY lower(email)
                HAVING count(*) > 1

                UNION ALL

                SELECT
                    'representatives' AS source_table,
                    lower(email) AS normalized_email,
                    count(*) AS quantity
                FROM representatives
                GROUP BY lower(email)
                HAVING count(*) > 1

                UNION ALL

                SELECT
                    'users' AS source_table,
                    lower(email) AS normalized_email,
                    count(*) AS quantity
                FROM users
                GROUP BY lower(email)
                HAVING count(*) > 1
            ) AS duplicates
            LIMIT 1
            """
        )
    ).mappings().first()
    if duplicate:
        raise RuntimeError(
            "Migração 0035 interrompida: existem e-mails duplicados em "
            f"{duplicate['source_table']} para "
            f"'{duplicate['normalized_email']}' "
            f"({duplicate['quantity']} registros). "
            "Corrija as duplicidades case-insensitive antes do deploy."
        )


def _assert_user_links_are_unique() -> None:
    if op.get_context().as_sql:
        return
    inconsistent = op.get_bind().execute(
        sa.text(
            """
            SELECT id, rep_id, linked_id
            FROM users
            WHERE role = 'representante'
              AND rep_id IS NOT NULL
              AND linked_id IS NOT NULL
              AND linked_id <> rep_id
            LIMIT 1
            """
        )
    ).mappings().first()
    if inconsistent:
        raise RuntimeError(
            "Migração 0035 interrompida: o usuário "
            f"'{inconsistent['id']}' possui rep_id e linked_id diferentes. "
            "Corrija o vínculo antes do deploy."
        )
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT effective_link_id, count(*) AS quantity
            FROM (
                SELECT
                    CASE
                        WHEN role = 'representante' AND rep_id IS NOT NULL
                            THEN rep_id
                        ELSE linked_id
                    END AS effective_link_id
                FROM users
            ) AS user_links
            WHERE effective_link_id IS NOT NULL
            GROUP BY effective_link_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).mappings().first()
    if duplicate:
        raise RuntimeError(
            "Migração 0035 interrompida: o vínculo "
            f"'{duplicate['effective_link_id']}' aparece em "
            f"{duplicate['quantity']} usuários. "
            "Mantenha somente uma conta por cliente/representante."
        )


def upgrade() -> None:
    _assert_normalized_emails_are_unique()
    _assert_user_links_are_unique()
    with op.get_context().autocommit_block():
        for name, table_name, columns in INDEXES:
            _drop_invalid_index(name, table_name)
            op.create_index(
                name,
                table_name,
                columns,
                unique=False,
                if_not_exists=True,
                postgresql_concurrently=True,
            )
        for name, table_name, expression, unique in EXPRESSION_INDEXES:
            _create_expression_index(
                name,
                table_name,
                expression,
                unique,
            )
        for name, table_name, column_name in TRGM_INDEXES:
            _drop_invalid_index(name, table_name)
            op.create_index(
                name,
                table_name,
                [column_name],
                unique=False,
                if_not_exists=True,
                postgresql_using="gin",
                postgresql_ops={column_name: "gin_trgm_ops"},
                postgresql_concurrently=True,
            )
        op.execute(
            """
            UPDATE users
            SET linked_id = rep_id
            WHERE role = 'representante'
              AND rep_id IS NOT NULL
              AND linked_id IS NULL
            """
        )
        _drop_invalid_index("uq_users_linked_id_not_null", "users")
        op.create_index(
            "uq_users_linked_id_not_null",
            "users",
            ["linked_id"],
            unique=True,
            if_not_exists=True,
            postgresql_where=sa.text("linked_id IS NOT NULL"),
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_users_linked_id",
            table_name="users",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.execute("ANALYZE clients")
        op.execute("ANALYZE representatives")
        op.execute("ANALYZE users")
        op.execute("ANALYZE products")
        op.execute("ANALYZE optionals")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_invalid_index("ix_users_linked_id", "users")
        op.create_index(
            "ix_users_linked_id",
            "users",
            ["linked_id"],
            unique=False,
            if_not_exists=True,
            postgresql_where=sa.text("linked_id IS NOT NULL"),
            postgresql_concurrently=True,
        )
        op.drop_index(
            "uq_users_linked_id_not_null",
            table_name="users",
            if_exists=True,
            postgresql_concurrently=True,
        )
        for name, table_name, _ in reversed(TRGM_INDEXES):
            op.drop_index(
                name,
                table_name=table_name,
                if_exists=True,
                postgresql_concurrently=True,
            )
        for name, table_name, _, _ in reversed(EXPRESSION_INDEXES):
            op.drop_index(
                name,
                table_name=table_name,
                if_exists=True,
                postgresql_concurrently=True,
            )
        for name, table_name, _ in reversed(INDEXES):
            op.drop_index(
                name,
                table_name=table_name,
                if_exists=True,
                postgresql_concurrently=True,
            )
