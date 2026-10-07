"""R9: auditoria das três alavancas de IPI em produtos BR

Revision ID: fiscal_audit_r9_20261007
Revises: uf_whitelist_r8_20261005
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op


revision = "fiscal_audit_r9_20261007"
down_revision = "uf_whitelist_r8_20261005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_group_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_group_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("group_name", sa.String(length=100), nullable=False),
        sa.Column("old_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("new_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["market_code"],
            ["markets.code"],
            name="fk_product_group_audit_market",
        ),
        sa.CheckConstraint(
            "market_code = 'BR'",
            name="ck_product_group_audit_br_only",
        ),
        sa.CheckConstraint(
            "action IN ('created', 'updated', 'deleted')",
            name="ck_product_group_audit_action",
        ),
        sa.CheckConstraint(
            "source IN ('api', 'csv')",
            name="ck_product_group_audit_source",
        ),
        sa.CheckConstraint(
            "(action = 'created' AND old_ipi IS NULL AND new_ipi IS NOT NULL) "
            "OR (action = 'updated' AND old_ipi IS NOT NULL AND new_ipi IS NOT NULL) "
            "OR (action = 'deleted' AND old_ipi IS NOT NULL AND new_ipi IS NULL)",
            name="ck_product_group_audit_values",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_group_audit_group_created",
        "product_group_audit_events",
        ["product_group_id", "created_at"],
    )
    op.create_index(
        "ix_product_group_audit_actor_created",
        "product_group_audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_product_group_audit_market_created",
        "product_group_audit_events",
        ["market_code", "created_at"],
    )
    op.create_table(
        "product_type_fiscal_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_type_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("old_name", sa.String(length=50), nullable=True),
        sa.Column("new_name", sa.String(length=50), nullable=True),
        sa.Column("old_group_id", sa.Uuid(), nullable=True),
        sa.Column("new_group_id", sa.Uuid(), nullable=True),
        sa.Column("old_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("new_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], name="fk_type_fiscal_audit_market"),
        sa.CheckConstraint("market_code = 'BR'", name="ck_type_fiscal_audit_br_only"),
        sa.CheckConstraint("action IN ('created', 'updated', 'deleted')", name="ck_type_fiscal_audit_action"),
        sa.CheckConstraint("source IN ('api', 'csv')", name="ck_type_fiscal_audit_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_type_fiscal_audit_type_created", "product_type_fiscal_audit_events",
        ["product_type_id", "created_at"],
    )
    op.create_index(
        "ix_type_fiscal_audit_actor_created", "product_type_fiscal_audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_table(
        "product_fiscal_assignment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("old_type", sa.String(length=50), nullable=True),
        sa.Column("new_type", sa.String(length=50), nullable=False),
        sa.Column("old_group_id", sa.Uuid(), nullable=True),
        sa.Column("new_group_id", sa.Uuid(), nullable=True),
        sa.Column("old_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("new_ipi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], name="fk_product_fiscal_assignment_market"),
        sa.CheckConstraint("market_code = 'BR'", name="ck_product_fiscal_assignment_br_only"),
        sa.CheckConstraint("action IN ('created', 'updated')", name="ck_product_fiscal_assignment_action"),
        sa.CheckConstraint("source IN ('api', 'csv')", name="ck_product_fiscal_assignment_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_fiscal_assignment_product_created", "product_fiscal_assignment_events",
        ["product_id", "created_at"],
    )
    op.create_index(
        "ix_product_fiscal_assignment_actor_created", "product_fiscal_assignment_events",
        ["actor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_fiscal_assignment_actor_created", table_name="product_fiscal_assignment_events")
    op.drop_index("ix_product_fiscal_assignment_product_created", table_name="product_fiscal_assignment_events")
    op.drop_table("product_fiscal_assignment_events")
    op.drop_index("ix_type_fiscal_audit_actor_created", table_name="product_type_fiscal_audit_events")
    op.drop_index("ix_type_fiscal_audit_type_created", table_name="product_type_fiscal_audit_events")
    op.drop_table("product_type_fiscal_audit_events")
    op.drop_index(
        "ix_product_group_audit_market_created",
        table_name="product_group_audit_events",
    )
    op.drop_index(
        "ix_product_group_audit_actor_created",
        table_name="product_group_audit_events",
    )
    op.drop_index(
        "ix_product_group_audit_group_created",
        table_name="product_group_audit_events",
    )
    op.drop_table("product_group_audit_events")
