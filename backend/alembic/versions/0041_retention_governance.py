"""add legal holds and non-destructive retention reviews

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_type IN ('client', 'representative', 'order')",
            name="ck_legal_holds_subject_type",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_legal_holds_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["released_by_user_id"],
            ["users.id"],
            name="fk_legal_holds_released_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legal_holds_subject_active",
        "legal_holds",
        ["subject_type", "subject_id", "released_at"],
    )
    op.create_index(
        "ix_legal_holds_expires_at",
        "legal_holds",
        ["expires_at"],
    )
    op.create_index(
        "ix_legal_holds_created_at",
        "legal_holds",
        ["created_at"],
    )

    op.create_table(
        "retention_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=30), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "candidate_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "truncated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved')",
            name="ck_retention_reviews_status",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0",
            name="ck_retention_reviews_candidate_count",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_retention_reviews_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_retention_reviews_approved_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_retention_reviews_created_at",
        "retention_reviews",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_retention_reviews_status_created",
        "retention_reviews",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_clients_retention_updated_id",
        "clients",
        ["updated_at", "id"],
    )
    op.create_index(
        "ix_orders_retention_open_updated_id",
        "orders",
        ["updated_at", "id"],
        postgresql_where=sa.text(
            "is_finalized = false AND is_cancelled = false"
        ),
    )
    op.create_index(
        "ix_orders_retention_closed_updated_id",
        "orders",
        ["updated_at", "id"],
        postgresql_where=sa.text(
            "is_finalized = true OR is_cancelled = true"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orders_retention_closed_updated_id",
        table_name="orders",
    )
    op.drop_index(
        "ix_orders_retention_open_updated_id",
        table_name="orders",
    )
    op.drop_index(
        "ix_clients_retention_updated_id",
        table_name="clients",
    )
    op.drop_index(
        "ix_retention_reviews_status_created",
        table_name="retention_reviews",
    )
    op.drop_index(
        "ix_retention_reviews_created_at",
        table_name="retention_reviews",
    )
    op.drop_table("retention_reviews")
    op.drop_index("ix_legal_holds_created_at", table_name="legal_holds")
    op.drop_index("ix_legal_holds_expires_at", table_name="legal_holds")
    op.drop_index(
        "ix_legal_holds_subject_active",
        table_name="legal_holds",
    )
    op.drop_table("legal_holds")
