"""expand order monetary capacity

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def _acquire_short_ddl_window() -> None:
    # O aumento de precisão é rápido, mas ALTER COLUMN exige ACCESS EXCLUSIVE.
    # Falhar cedo permite que o deploy seja repetido sem manter requisições
    # enfileiradas atrás de uma transação longa.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(
        "LOCK TABLE orders, order_items "
        "IN ACCESS EXCLUSIVE MODE"
    )


def upgrade() -> None:
    _acquire_short_ddl_window()
    wide_money = sa.Numeric(20, 2)
    current_money = sa.Numeric(12, 2)
    for column_name in (
        "total_value",
        "total_ipi",
        "total_with_ipi",
    ):
        op.alter_column(
            "orders",
            column_name,
            existing_type=current_money,
            type_=wide_money,
            existing_nullable=False,
        )
    op.alter_column(
        "order_items",
        "ipi_value",
        existing_type=current_money,
        type_=wide_money,
        existing_nullable=False,
    )


def downgrade() -> None:
    _acquire_short_ddl_window()
    current_money = sa.Numeric(20, 2)
    narrow_money = sa.Numeric(12, 2)
    op.alter_column(
        "order_items",
        "ipi_value",
        existing_type=current_money,
        type_=narrow_money,
        existing_nullable=False,
    )
    for column_name in (
        "total_with_ipi",
        "total_ipi",
        "total_value",
    ):
        op.alter_column(
            "orders",
            column_name,
            existing_type=current_money,
            type_=narrow_money,
            existing_nullable=False,
        )
