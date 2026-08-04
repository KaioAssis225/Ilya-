"""make PED numbering sequential per creating user

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-04
"""

import sqlalchemy as sa
from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


_LEGACY_GLOBAL_OWNER = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("number_owner_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("order_number", sa.Integer(), nullable=True),
    )
    # A exclusividade global precisa sair antes de renumerar: PED-0001 passa a
    # existir legitimamente em mais de um escopo de usuário.
    op.drop_constraint("orders_code_key", "orders", type_="unique")

    # Pedidos legados não registravam o criador. Atribui-se primeiro a conta do
    # representante, depois a conta do cliente e, por fim, o escopo legado.
    # Dentro de cada escopo, o histórico é renumerado cronologicamente; o ORC,
    # que é a identificação global compartilhada, não é alterado.
    op.execute(
        sa.text(
            f"""
            WITH attributed AS (
                SELECT
                    current_order.id,
                    current_order.created_at,
                    COALESCE(
                        (
                            SELECT rep_user.id
                            FROM users AS rep_user
                            WHERE rep_user.role = 'representante'
                              AND rep_user.rep_id = current_order.rep_id
                            ORDER BY rep_user.created_at, rep_user.id
                            LIMIT 1
                        ),
                        (
                            SELECT client_user.id
                            FROM users AS client_user
                            WHERE client_user.linked_id = current_order.client_id
                              AND client_user.role IN ('cliente', 'vendedor')
                            ORDER BY client_user.created_at, client_user.id
                            LIMIT 1
                        ),
                        '{_LEGACY_GLOBAL_OWNER}'::uuid
                    ) AS owner_id
                FROM orders AS current_order
            ),
            numbered AS (
                SELECT
                    id,
                    owner_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY owner_id
                        ORDER BY created_at, id
                    )::integer AS local_number
                FROM attributed
            )
            UPDATE orders AS current_order
            SET
                number_owner_id = numbered.owner_id,
                order_number = numbered.local_number,
                code = 'PED-' || LPAD(numbered.local_number::text, 4, '0')
            FROM numbered
            WHERE current_order.id = numbered.id
            """
        )
    )

    op.alter_column("orders", "number_owner_id", nullable=False)
    op.alter_column("orders", "order_number", nullable=False)
    op.create_check_constraint(
        "ck_orders_order_number_positive",
        "orders",
        "order_number > 0",
    )
    op.create_unique_constraint(
        "uq_orders_number_owner_order_number",
        "orders",
        ["number_owner_id", "order_number"],
    )
    op.create_index(
        "ix_orders_number_owner_id",
        "orders",
        ["number_owner_id"],
    )
    op.create_table(
        "order_number_counters",
        sa.Column("number_owner_id", sa.Uuid(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "number_owner_id",
            name="pk_order_number_counters",
        ),
        sa.CheckConstraint(
            "next_value > 0",
            name="ck_order_number_counters_next_value_positive",
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO order_number_counters (number_owner_id, next_value)
            SELECT number_owner_id, MAX(order_number) + 1
            FROM orders
            GROUP BY number_owner_id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_code = bind.execute(
        sa.text(
            """
            SELECT code
            FROM orders
            GROUP BY code
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate_code:
        raise RuntimeError(
            "Downgrade 0038 não é seguro: existem códigos PED repetidos "
            f"entre usuários (exemplo: {duplicate_code})."
        )

    op.drop_table("order_number_counters")
    op.drop_index("ix_orders_number_owner_id", table_name="orders")
    op.drop_constraint(
        "uq_orders_number_owner_order_number",
        "orders",
        type_="unique",
    )
    op.drop_constraint(
        "ck_orders_order_number_positive",
        "orders",
        type_="check",
    )
    op.create_unique_constraint("orders_code_key", "orders", ["code"])
    op.drop_column("orders", "order_number")
    op.drop_column("orders", "number_owner_id")
