"""add structured privacy event audit trail

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-05
"""

import sqlalchemy as sa
from alembic import op


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privacy_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "outcome",
            sa.String(length=20),
            server_default="completed",
            nullable=False,
        ),
        sa.Column("legal_basis", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_privacy_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_events_created_id",
        "privacy_events",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_privacy_events_subject",
        "privacy_events",
        ["subject_type", "subject_id"],
    )
    op.create_index(
        "ix_privacy_events_actor_user_id",
        "privacy_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_privacy_events_action_created",
        "privacy_events",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_privacy_events_action_created",
        table_name="privacy_events",
    )
    op.drop_index(
        "ix_privacy_events_actor_user_id",
        table_name="privacy_events",
    )
    op.drop_index("ix_privacy_events_subject", table_name="privacy_events")
    op.drop_index("ix_privacy_events_created_id", table_name="privacy_events")
    op.drop_table("privacy_events")
