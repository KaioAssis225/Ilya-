"""Remove permanently the electronic order-signature feature.

This migration permanently deletes signature data (business decision 2026-10-21).
The downgrade only recreates empty structures; historical signature blobs and
signature evidence will not be recovered.

Revision ID: remove_order_signatures_r20
Revises: p11_benchmark_readonly
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "remove_order_signatures_r20"
down_revision = "p11_benchmark_readonly"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS order_signature_evidence")
    op.execute("DROP TABLE IF EXISTS signature_invitations")
    op.execute(
        "ALTER TABLE orders DROP COLUMN IF EXISTS rep_signature, "
        "DROP COLUMN IF EXISTS client_signature"
    )


def downgrade() -> None:
    op.add_column("orders", sa.Column("client_signature", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("rep_signature", sa.Text(), nullable=True))

    op.create_table(
        "signature_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("document_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("verification_method", sa.String(length=30), nullable=True),
        sa.Column("issued_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_signature_invitations_order_id",
        "signature_invitations",
        ["order_id"],
    )
    op.create_index(
        "ix_signature_invitations_client_id",
        "signature_invitations",
        ["client_id"],
    )
    op.create_index(
        "ix_signature_invitations_token_hash",
        "signature_invitations",
        ["token_hash"],
    )
    op.create_index(
        "ix_signature_invitations_expires_at",
        "signature_invitations",
        ["expires_at"],
    )
    op.create_index(
        "ix_signature_invitations_issued_by",
        "signature_invitations",
        ["issued_by"],
    )

    op.create_table(
        "order_signature_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("signer_kind", sa.String(20), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("document_hash", sa.String(64), nullable=True),
        sa.Column("signature_hash", sa.String(64), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "signer_kind", name="uq_order_signature_evidence_signer"),
    )
    op.create_index(
        "ix_order_signature_evidence_order_id",
        "order_signature_evidence",
        ["order_id"],
    )
