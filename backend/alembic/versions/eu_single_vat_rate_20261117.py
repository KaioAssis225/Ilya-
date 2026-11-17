"""IVA único do mercado EU: taxa em markets, snapshot no pedido e trilha de mudanças

Revision ID: eu_single_vat_rate_20261117
Revises: showroom_item_options_r49
Create Date: 2026-11-17

Em Portugal o IVA é cobrado uma só vez, sobre o total do documento (não por
produto, como o ICMS). Esta migração é só aditiva:

- `markets.vat_rate`: a taxa única do mercado (EU = 23,00, a taxa padrão de
  Portugal já usada em todos os SKUs aprovados). BR fica NULL: segue com IPI por grupo.
- `orders.vat_rate`: a taxa usada no documento. NULL = documento antigo, com IVA
  por linha, que nunca é recalculado.
- `market_vat_rate_events`: quem mudou a taxa, quando, de quanto para quanto.

As colunas de IVA por produto em `product_markets` não são tocadas.
"""
from alembic import op
import sqlalchemy as sa


revision = "eu_single_vat_rate_20261117"
down_revision = "showroom_item_options_r49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True))
    op.create_check_constraint(
        "ck_markets_vat_rate_range",
        "markets",
        "vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)",
    )
    op.execute(sa.text("UPDATE markets SET vat_rate = 23.00 WHERE code = 'EU'"))

    op.add_column("orders", sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True))
    op.create_check_constraint(
        "ck_orders_vat_rate_range",
        "orders",
        "vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)",
    )

    op.create_table(
        "market_vat_rate_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        # Histórico sem FK: apagar a conta não pode apagar quem mudou a taxa.
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("old_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("new_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], name="fk_market_vat_rate_events_market"),
        sa.CheckConstraint("market_code = 'EU'", name="ck_market_vat_rate_events_eu_only"),
        sa.CheckConstraint("new_rate >= 0 AND new_rate <= 100", name="ck_market_vat_rate_events_new_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_vat_rate_events_market_created",
        "market_vat_rate_events",
        ["market_code", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_vat_rate_events_market_created", table_name="market_vat_rate_events")
    op.drop_table("market_vat_rate_events")
    op.drop_constraint("ck_orders_vat_rate_range", "orders", type_="check")
    op.drop_column("orders", "vat_rate")
    op.drop_constraint("ck_markets_vat_rate_range", "markets", type_="check")
    op.drop_column("markets", "vat_rate")
