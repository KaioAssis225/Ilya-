"""add mandatory privacy incident registry

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privacy_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="investigating",
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("data_categories", sa.JSON(), nullable=False),
        sa.Column("affected_subjects_count", sa.Integer(), nullable=True),
        sa.Column("risk_assessment", sa.Text(), nullable=False),
        sa.Column("mitigation_measures", sa.Text(), nullable=False),
        sa.Column(
            "anpd_notified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "subjects_notified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("notification_details", sa.Text(), nullable=True),
        sa.Column("non_notification_reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence_references",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_actions", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('investigating', 'contained', 'closed')",
            name="ck_privacy_incidents_status",
        ),
        sa.CheckConstraint(
            "affected_subjects_count IS NULL OR affected_subjects_count >= 0",
            name="ck_privacy_incidents_affected_count",
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name="ck_privacy_incidents_closed_timestamp",
        ),
        sa.CheckConstraint(
            "retain_until >= created_at + INTERVAL '5 years'",
            name="ck_privacy_incidents_minimum_retention",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_incidents_known_id",
        "privacy_incidents",
        ["known_at", "id"],
    )
    op.create_index(
        "ix_privacy_incidents_status_known",
        "privacy_incidents",
        ["status", "known_at"],
    )
    op.create_index(
        "ix_privacy_incidents_retain_until",
        "privacy_incidents",
        ["retain_until", "id"],
    )
    op.create_index(
        "ix_privacy_incidents_created_by",
        "privacy_incidents",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_privacy_incidents_created_by",
        table_name="privacy_incidents",
    )
    op.drop_index(
        "ix_privacy_incidents_retain_until",
        table_name="privacy_incidents",
    )
    op.drop_index(
        "ix_privacy_incidents_status_known",
        table_name="privacy_incidents",
    )
    op.drop_index(
        "ix_privacy_incidents_known_id",
        table_name="privacy_incidents",
    )
    op.drop_table("privacy_incidents")
