"""governanca fiscal do IVA europeu: status, origem e trilha de aprovacao

Revision ID: vat_approval_20261001
Revises: catalogs_20260911
Create Date: 2026-10-01

Adiciona a product_markets o ciclo de aprovacao do IVA de Portugal. A taxa
isolada deixa de ser faturavel: so vale quando aprovada por uma pessoa, com
autor e data. O legado fica `pending`/`legacy_unknown` (sem forjar origem
aprovada). BR nao usa estes campos — fica `pending` sem efeito, continua no IPI.
"""
from alembic import op
import sqlalchemy as sa


revision = "vat_approval_20261001"
down_revision = "catalogs_20260911"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Colunas nullable primeiro, para preencher o legado antes de travar.
    op.add_column("product_markets", sa.Column("vat_status", sa.String(length=20), nullable=True))
    op.add_column("product_markets", sa.Column("vat_source", sa.String(length=20), nullable=True))
    op.add_column(
        "product_markets",
        sa.Column("approved_by_user_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "product_markets",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_markets_approved_by_user_id",
        "product_markets",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 2) Backfill do legado: tudo vira `pending` com origem desconhecida. Nenhuma
    #    linha existente ganha autor/data — nao houve aprovacao humana.
    op.execute(
        sa.text(
            "UPDATE product_markets "
            "SET vat_status = 'pending', vat_source = 'legacy_unknown' "
            "WHERE vat_status IS NULL OR vat_source IS NULL"
        )
    )

    # 3) Agora que nao ha nulos, trava NOT NULL com default para novas linhas.
    op.alter_column(
        "product_markets",
        "vat_status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="pending",
    )
    op.alter_column(
        "product_markets",
        "vat_source",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="legacy_unknown",
    )

    # 4) Aprovacao indivisivel: autor+data existem se, e so se, `approved`, e
    #    `approved` exige a taxa. O legado `pending` passa sem fingir aprovacao.
    op.create_check_constraint(
        "ck_product_markets_vat_approval",
        "product_markets",
        "(vat_status = 'approved' AND vat_rate IS NOT NULL "
        "AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL) "
        "OR (vat_status IN ('pending', 'rejected') "
        "AND approved_by_user_id IS NULL AND approved_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_markets_vat_approval", "product_markets", type_="check")
    op.drop_constraint("fk_product_markets_approved_by_user_id", "product_markets", type_="foreignkey")
    op.drop_column("product_markets", "approved_at")
    op.drop_column("product_markets", "approved_by_user_id")
    op.drop_column("product_markets", "vat_source")
    op.drop_column("product_markets", "vat_status")
