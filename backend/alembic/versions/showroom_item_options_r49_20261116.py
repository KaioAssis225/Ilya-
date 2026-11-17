"""Permite configurações independentes do mesmo produto no Estoque EU.

Cada linha mantém um snapshot JSON dos opcionais escolhidos e uma chave
canônica. A unicidade passa de produto para produto + configuração, permitindo
o mesmo SKU com acabamentos diferentes sem duplicar o catálogo mestre.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "showroom_item_options_r49"
down_revision = "rename_showroom_stock_r48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "showroom_box_items",
        sa.Column(
            "optional_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "showroom_box_items",
        sa.Column(
            "configuration_key",
            sa.String(64),
            nullable=False,
            server_default="base",
        ),
    )
    op.drop_constraint(
        "uq_showroom_box_items_product",
        "showroom_box_items",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_showroom_box_items_configuration",
        "showroom_box_items",
        ["box_id", "product_id", "configuration_key"],
    )


def downgrade() -> None:
    # Configurações distintas do mesmo produto não cabem no contrato anterior.
    # Consolida quantidades antes de restaurar a unicidade antiga.
    op.execute(sa.text(
        "WITH totals AS ("
        " SELECT box_id, product_id, min(id::text)::uuid AS keep_id, sum(quantity) AS quantity"
        " FROM showroom_box_items GROUP BY box_id, product_id"
        ") UPDATE showroom_box_items i SET quantity = totals.quantity"
        " FROM totals WHERE i.id = totals.keep_id"
    ))
    op.execute(sa.text(
        "DELETE FROM showroom_box_items i USING ("
        " SELECT box_id, product_id, min(id::text)::uuid AS keep_id"
        " FROM showroom_box_items GROUP BY box_id, product_id"
        ") keep WHERE i.box_id = keep.box_id AND i.product_id = keep.product_id"
        " AND i.id <> keep.keep_id"
    ))
    op.drop_constraint(
        "uq_showroom_box_items_configuration",
        "showroom_box_items",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_showroom_box_items_product",
        "showroom_box_items",
        ["box_id", "product_id"],
    )
    op.drop_column("showroom_box_items", "configuration_key")
    op.drop_column("showroom_box_items", "optional_configuration")
