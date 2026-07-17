"""add scale-oriented indexes and remove redundant indexes

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _assert_constraint_data_is_ready() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    invalid_uf = bind.execute(
        sa.text(
            """
            SELECT source_table, id, state
            FROM (
                SELECT 'clients' AS source_table, id, state
                FROM clients
                WHERE state IS NULL
                   OR upper(btrim(state)) !~ '^[A-Z]{2}$'

                UNION ALL

                SELECT 'representatives' AS source_table, id, state
                FROM representatives
                WHERE state IS NULL
                   OR upper(btrim(state)) !~ '^[A-Z]{2}$'
            ) AS invalid_states
            LIMIT 1
            """
        )
    ).mappings().first()
    if invalid_uf:
        raise RuntimeError(
            "Migração 0033 interrompida: UF inválida em "
            f"{invalid_uf['source_table']} id={invalid_uf['id']} "
            f"valor={invalid_uf['state']!r}. Corrija os dados antes do deploy."
        )

    conflicting_order = bind.execute(
        sa.text(
            """
            SELECT id, code
            FROM orders
            WHERE is_finalized IS TRUE
              AND is_cancelled IS TRUE
            LIMIT 1
            """
        )
    ).mappings().first()
    if conflicting_order:
        raise RuntimeError(
            "Migração 0033 interrompida: pedido "
            f"{conflicting_order['code']} ({conflicting_order['id']}) está "
            "finalizado e cancelado ao mesmo tempo."
        )


def _create(
    name: str,
    table: str,
    columns: list[str],
    *,
    where: str | None = None,
    using: str | None = None,
    ops: dict[str, str] | None = None,
) -> None:
    # Uma interrupção durante CREATE INDEX CONCURRENTLY pode deixar um índice
    # inválido. IF NOT EXISTS sozinho o preservaria e ocultaria o problema.
    if not op.get_context().as_sql:
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
                table_name=table,
                if_exists=True,
                postgresql_concurrently=True,
            )
    dialect_options = {}
    if where:
        dialect_options["postgresql_where"] = sa.text(where)
    if using:
        dialect_options["postgresql_using"] = using
    if ops:
        dialect_options["postgresql_ops"] = ops
    op.create_index(
        name,
        table,
        columns,
        unique=False,
        if_not_exists=True,
        postgresql_concurrently=True,
        **dialect_options,
    )


def upgrade() -> None:
    _assert_constraint_data_is_ready()
    # CREATE/DROP INDEX CONCURRENTLY não pode executar dentro da transação DDL
    # padrão do Alembic. Isso reduz bloqueios de escrita durante o deploy.
    with op.get_context().autocommit_block():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "UPDATE clients SET state = upper(btrim(state)) "
            "WHERE state IS DISTINCT FROM upper(btrim(state))"
        )
        op.execute(
            "UPDATE representatives SET state = upper(btrim(state)) "
            "WHERE state IS DISTINCT FROM upper(btrim(state))"
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_clients_state_uf'
                      AND conrelid = 'clients'::regclass
                ) THEN
                    ALTER TABLE clients
                    ADD CONSTRAINT ck_clients_state_uf
                    CHECK (state ~ '^[A-Z]{2}$')
                    NOT VALID;
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_representatives_state_uf'
                      AND conrelid = 'representatives'::regclass
                ) THEN
                    ALTER TABLE representatives
                    ADD CONSTRAINT ck_representatives_state_uf
                    CHECK (state ~ '^[A-Z]{2}$')
                    NOT VALID;
                END IF;
            END
            $$;
            """
        )
        op.execute(
            "ALTER TABLE clients VALIDATE CONSTRAINT ck_clients_state_uf"
        )
        op.execute(
            "ALTER TABLE representatives "
            "VALIDATE CONSTRAINT ck_representatives_state_uf"
        )
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_orders_single_terminal_status'
                      AND conrelid = 'orders'::regclass
                ) THEN
                    ALTER TABLE orders
                    ADD CONSTRAINT ck_orders_single_terminal_status
                    CHECK (NOT (is_finalized AND is_cancelled))
                    NOT VALID;
                END IF;
            END
            $$;
            """
        )
        op.execute(
            "ALTER TABLE orders "
            "VALIDATE CONSTRAINT ck_orders_single_terminal_status"
        )
        _create(
            "ix_orders_code_trgm",
            "orders",
            ["code"],
            using="gin",
            ops={"code": "gin_trgm_ops"},
        )
        _create(
            "ix_orders_orc_id_trgm",
            "orders",
            ["orc_id"],
            using="gin",
            ops={"orc_id": "gin_trgm_ops"},
        )
        _create(
            "ix_clients_name_trgm",
            "clients",
            ["name"],
            using="gin",
            ops={"name": "gin_trgm_ops"},
        )
        _create(
            "ix_representatives_name_trgm",
            "representatives",
            ["name"],
            using="gin",
            ops={"name": "gin_trgm_ops"},
        )
        _create(
            "ix_products_search_trgm",
            "products",
            ["product_code", "description"],
            using="gin",
            ops={
                "product_code": "gin_trgm_ops",
                "description": "gin_trgm_ops",
            },
        )
        _create("ix_orders_created_id", "orders", ["created_at", "id"])
        _create(
            "ix_orders_client_created_id",
            "orders",
            ["client_id", "created_at", "id"],
        )
        _create(
            "ix_orders_rep_created_id",
            "orders",
            ["rep_id", "created_at", "id"],
            where="rep_id IS NOT NULL",
        )
        _create(
            "ix_orders_open_created_id",
            "orders",
            ["created_at", "id"],
            where="is_finalized = false AND is_cancelled = false",
        )
        _create(
            "ix_orders_finalized_created_id",
            "orders",
            ["created_at", "id"],
            where="is_finalized = true",
        )
        _create(
            "ix_orders_cancelled_created_id",
            "orders",
            ["created_at", "id"],
            where="is_cancelled = true",
        )
        _create("ix_order_items_order_id", "order_items", ["order_id"])
        _create("ix_clients_rep_id", "clients", ["rep_id"])
        _create("ix_clients_state_id", "clients", ["state", "id"])
        _create("ix_users_rep_id", "users", ["rep_id"])
        _create(
            "ix_users_linked_id",
            "users",
            ["linked_id"],
            where="linked_id IS NOT NULL",
        )
        _create(
            "ix_order_history_created_id",
            "order_history",
            ["created_at", "id"],
        )
        _create(
            "ix_order_history_order_created_id",
            "order_history",
            ["order_id", "created_at", "id"],
        )
        _create("ix_order_history_user_id", "order_history", ["user_id"])
        _create(
            "ix_notifications_user_created",
            "notifications",
            ["user_id", "created_at"],
        )
        _create("ix_refresh_tokens_parent_id", "refresh_tokens", ["parent_id"])
        _create(
            "ix_refresh_tokens_active_user_created",
            "refresh_tokens",
            ["user_id", "created_at"],
            where="revoked = false",
        )
        _create(
            "ix_product_optionals_optional_id",
            "product_optionals",
            ["optional_id"],
        )
        _create(
            "ix_product_set_items_product_id",
            "product_set_items",
            ["product_id"],
        )
        _create(
            "ix_product_set_component_optionals_optional_id",
            "product_set_component_optionals",
            ["optional_id"],
        )
        _create("ix_product_types_group_id", "product_types", ["group_id"])
        _create(
            "ix_signature_invitations_issued_by",
            "signature_invitations",
            ["issued_by"],
        )

        # As constraints UNIQUE já mantêm índices equivalentes.
        for name, table in (
            ("ix_orders_code", "orders"),
            ("ix_orders_orc_id", "orders"),
            ("ix_products_product_code", "products"),
            ("ix_users_username", "users"),
            ("ix_signature_invitations_token_hash", "signature_invitations"),
            ("ix_notifications_user_id", "notifications"),
            ("ix_order_history_order_id", "order_history"),
        ):
            op.drop_index(
                name,
                table_name=table,
                if_exists=True,
                postgresql_concurrently=True,
            )

        op.execute(
            "ANALYZE orders, order_items, order_history, clients, users, "
            "notifications, refresh_tokens, products"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TABLE representatives "
            "DROP CONSTRAINT IF EXISTS ck_representatives_state_uf"
        )
        op.execute(
            "ALTER TABLE clients "
            "DROP CONSTRAINT IF EXISTS ck_clients_state_uf"
        )
        op.execute(
            "ALTER TABLE orders "
            "DROP CONSTRAINT IF EXISTS ck_orders_single_terminal_status"
        )
        for name, table in (
            ("ix_products_search_trgm", "products"),
            ("ix_representatives_name_trgm", "representatives"),
            ("ix_clients_name_trgm", "clients"),
            ("ix_orders_orc_id_trgm", "orders"),
            ("ix_orders_code_trgm", "orders"),
            ("ix_signature_invitations_issued_by", "signature_invitations"),
            ("ix_product_types_group_id", "product_types"),
            (
                "ix_product_set_component_optionals_optional_id",
                "product_set_component_optionals",
            ),
            ("ix_product_set_items_product_id", "product_set_items"),
            ("ix_product_optionals_optional_id", "product_optionals"),
            ("ix_refresh_tokens_active_user_created", "refresh_tokens"),
            ("ix_refresh_tokens_parent_id", "refresh_tokens"),
            ("ix_notifications_user_created", "notifications"),
            ("ix_order_history_user_id", "order_history"),
            ("ix_order_history_order_created_id", "order_history"),
            ("ix_order_history_created_id", "order_history"),
            ("ix_users_linked_id", "users"),
            ("ix_users_rep_id", "users"),
            ("ix_clients_state_id", "clients"),
            ("ix_clients_rep_id", "clients"),
            ("ix_order_items_order_id", "order_items"),
            ("ix_orders_cancelled_created_id", "orders"),
            ("ix_orders_finalized_created_id", "orders"),
            ("ix_orders_open_created_id", "orders"),
            ("ix_orders_rep_created_id", "orders"),
            ("ix_orders_client_created_id", "orders"),
            ("ix_orders_created_id", "orders"),
        ):
            op.drop_index(
                name,
                table_name=table,
                if_exists=True,
                postgresql_concurrently=True,
            )

        _create("ix_orders_code", "orders", ["code"])
        _create("ix_orders_orc_id", "orders", ["orc_id"])
        _create("ix_products_product_code", "products", ["product_code"])
        _create("ix_users_username", "users", ["username"])
        _create(
            "ix_signature_invitations_token_hash",
            "signature_invitations",
            ["token_hash"],
        )
        _create("ix_notifications_user_id", "notifications", ["user_id"])
        _create("ix_order_history_order_id", "order_history", ["order_id"])
