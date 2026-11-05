"""Contatos adicionais do cliente (tabela client_contacts)."""

from alembic import op
import sqlalchemy as sa

revision = "client_contacts_r40"
down_revision = "client_contacted_r39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id", sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_client_contacts_client_position", "client_contacts", ["client_id", "position"]
    )


def downgrade() -> None:
    op.drop_index("ix_client_contacts_client_position", table_name="client_contacts")
    op.drop_table("client_contacts")
