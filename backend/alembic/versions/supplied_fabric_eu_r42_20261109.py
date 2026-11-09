"""TECIDO FORNECIDO (Portugal): preços sem tecido e metragem por produto EU.

Só estrutura, sem dados: os valores da planilha entram pela rota de importação
(`POST /api/v1/markets/EU/supplied-fabric/import`, com dry-run), nunca por esta
migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "supplied_fabric_eu_r42"
down_revision = "order_item_attachments_r41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_supplied_fabric",
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("linear_meters", sa.Numeric(8, 2), nullable=False),
        sa.Column("price_lojista", sa.Numeric(20, 2), nullable=False),
        sa.Column("price_corporativo", sa.Numeric(20, 2), nullable=False),
        sa.Column("price_pvp", sa.Numeric(20, 2), nullable=False),
        sa.Column("price_arquiteto", sa.Numeric(20, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("linear_meters > 0", name="ck_product_supplied_fabric_meters"),
        sa.CheckConstraint(
            "price_lojista >= 0 AND price_corporativo >= 0 AND price_pvp >= 0 AND price_arquiteto >= 0",
            name="ck_product_supplied_fabric_prices",
        ),
    )
    op.add_column("order_items", sa.Column("supplied_fabric_meters", sa.Numeric(8, 2), nullable=True))
    op.add_column(
        "order_item_optional_choices",
        sa.Column("supplied_fabric", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("order_item_optional_choices", "supplied_fabric")
    op.drop_column("order_items", "supplied_fabric_meters")
    op.drop_table("product_supplied_fabric")
