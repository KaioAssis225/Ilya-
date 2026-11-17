"""Histórico de transferências do Estoque EU (showroom → showroom ou orçamento).

Migração aditiva: só cria a tabela ``showroom_transfers``. Nenhum dado existente
muda; o downgrade apenas remove a tabela de histórico.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "showroom_transfers_20261117"
down_revision = "eu_single_vat_rate_20261117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "showroom_transfers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("market_code", sa.String(2), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("source_box_id", sa.Uuid(), sa.ForeignKey("showroom_boxes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_box_name", sa.String(120), nullable=False),
        sa.Column("destination_type", sa.String(10), nullable=False),
        sa.Column("destination_box_id", sa.Uuid(), sa.ForeignKey("showroom_boxes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("destination_box_name", sa.String(120), nullable=True),
        sa.Column("destination_order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("destination_order_code", sa.String(50), nullable=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_code", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "optional_configuration", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("market_code = 'EU'", name="ck_showroom_transfers_eu"),
        sa.CheckConstraint("quantity > 0", name="ck_showroom_transfers_quantity"),
        sa.CheckConstraint("destination_type IN ('box', 'order')", name="ck_showroom_transfers_type"),
    )
    op.create_index("ix_showroom_transfers_source", "showroom_transfers", ["source_box_id", "created_at"])
    op.create_index("ix_showroom_transfers_destination", "showroom_transfers", ["destination_box_id", "created_at"])
    op.create_index("ix_showroom_transfers_order", "showroom_transfers", ["destination_order_id"])


def downgrade() -> None:
    op.drop_index("ix_showroom_transfers_order", table_name="showroom_transfers")
    op.drop_index("ix_showroom_transfers_destination", table_name="showroom_transfers")
    op.drop_index("ix_showroom_transfers_source", table_name="showroom_transfers")
    op.drop_table("showroom_transfers")
