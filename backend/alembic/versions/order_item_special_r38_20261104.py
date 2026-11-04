"""Especial por item de orçamento no mercado EU."""

from alembic import op
import sqlalchemy as sa

revision = "order_item_special_r38"
down_revision = "eu_free_country_iroko_r37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("is_special", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("order_items", sa.Column("special_code", sa.String(length=100), nullable=True))
    op.add_column("order_items", sa.Column("special_percent", sa.Numeric(7, 2), nullable=True))
    op.create_check_constraint(
        "ck_order_items_special_consistent", "order_items",
        "(is_special AND special_code IS NOT NULL AND special_percent IS NOT NULL) OR "
        "(NOT is_special AND special_code IS NULL AND special_percent IS NULL)",
    )
    op.create_check_constraint(
        "ck_order_items_special_percent_valid", "order_items",
        "special_percent IS NULL OR (special_percent > -100 AND special_percent <= 1000)",
    )
    op.create_index(
        "uq_order_items_order_special_code", "order_items", ["order_id", "special_code"],
        unique=True, postgresql_where=sa.text("special_code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_order_items_order_special_code", table_name="order_items")
    op.drop_constraint("ck_order_items_special_percent_valid", "order_items", type_="check")
    op.drop_constraint("ck_order_items_special_consistent", "order_items", type_="check")
    op.drop_column("order_items", "special_percent")
    op.drop_column("order_items", "special_code")
    op.drop_column("order_items", "is_special")
