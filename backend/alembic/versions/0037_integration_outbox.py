"""integration outbox (estradas de integracao Ilya -> Ilya Estoque)

Tabela nova e isolada: nasce vazia, nenhuma tabela existente e alterada.
Nao ha backfill e o indice parcial e instantaneo numa tabela vazia.

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "event_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed', 'dead_letter')",
            name="ck_integration_outbox_status",
        ),
        sa.UniqueConstraint("event_id", name="uq_integration_outbox_event_id"),
    )

    # Indice quente do worker: "o que esta pronto para enviar agora?".
    # Parcial de proposito: as linhas 'delivered' viram a maioria da tabela com
    # o tempo e ficam fora do indice, que assim permanece pequeno.
    op.create_index(
        "ix_integration_outbox_due",
        "integration_outbox",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_due", table_name="integration_outbox")
    op.drop_table("integration_outbox")
