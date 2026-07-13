"""add persistent single-use signature invitations

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signature_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_signature_invitations_order_id", "signature_invitations", ["order_id"])
    op.create_index("ix_signature_invitations_client_id", "signature_invitations", ["client_id"])
    op.create_index("ix_signature_invitations_token_hash", "signature_invitations", ["token_hash"])
    op.create_index("ix_signature_invitations_expires_at", "signature_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_signature_invitations_expires_at", table_name="signature_invitations")
    op.drop_index("ix_signature_invitations_token_hash", table_name="signature_invitations")
    op.drop_index("ix_signature_invitations_client_id", table_name="signature_invitations")
    op.drop_index("ix_signature_invitations_order_id", table_name="signature_invitations")
    op.drop_table("signature_invitations")
