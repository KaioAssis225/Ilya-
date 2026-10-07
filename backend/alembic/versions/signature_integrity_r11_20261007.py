"""Vincula assinaturas futuras à versão e ao hash dos termos do pedido.

Revision ID: signature_integrity_r11_20261007
Revises: client_invites_r10_20261007
"""

import sqlalchemy as sa
from alembic import op


revision = "signature_integrity_r11_20261007"
down_revision = "client_invites_r10_20261007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("document_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("orders", sa.Column("supersedes_order_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("revision_number", sa.Integer(), server_default="1", nullable=False))
    op.create_foreign_key("fk_orders_supersedes_order", "orders", "orders", ["supersedes_order_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_orders_supersedes_order_id", "orders", ["supersedes_order_id"])
    op.add_column("signature_invitations", sa.Column("document_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("signature_invitations", sa.Column("recipient_email", sa.String(255), nullable=True))
    op.add_column("signature_invitations", sa.Column("verified_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("signature_invitations", sa.Column("verification_method", sa.String(30), nullable=True))
    op.add_column("signature_invitations", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    # Convites antigos eram devolvidos a operadores; não podem ser aproveitados.
    op.execute("""UPDATE signature_invitations SET revoked_at = now()
        WHERE consumed_at IS NULL AND revoked_at IS NULL""")

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
    op.create_index("ix_order_signature_evidence_order_id", "order_signature_evidence", ["order_id"])
    # O banco antigo não registrava o documento, a data nem a identidade do
    # assinante. Não inventar um hash histórico: marcar para revisão humana.
    op.execute("""INSERT INTO order_signature_evidence
        (id, order_id, signer_kind, method, verification_status)
        SELECT gen_random_uuid(), id, 'representative', 'legacy_unknown', 'unverified'
        FROM orders WHERE rep_signature IS NOT NULL""")
    op.execute("""INSERT INTO order_signature_evidence
        (id, order_id, signer_kind, method, verification_status)
        SELECT gen_random_uuid(), id, 'client', 'legacy_unknown', 'unverified'
        FROM orders WHERE client_signature IS NOT NULL""")


def downgrade() -> None:
    op.drop_index("ix_order_signature_evidence_order_id", table_name="order_signature_evidence")
    op.drop_table("order_signature_evidence")
    op.drop_column("signature_invitations", "sent_at")
    op.drop_column("signature_invitations", "verification_method")
    op.drop_column("signature_invitations", "verified_by_user_id")
    op.drop_column("signature_invitations", "recipient_email")
    op.drop_column("signature_invitations", "document_version")
    op.drop_column("orders", "document_version")
    op.drop_constraint("uq_orders_supersedes_order_id", "orders", type_="unique")
    op.drop_constraint("fk_orders_supersedes_order", "orders", type_="foreignkey")
    op.drop_column("orders", "revision_number")
    op.drop_column("orders", "supersedes_order_id")
