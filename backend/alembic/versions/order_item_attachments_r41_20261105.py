"""Anexos privados nos comentários dos itens do orçamento."""

from alembic import op
import sqlalchemy as sa


revision = "order_item_attachments_r41"
down_revision = "client_contacts_r40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_item_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_item_id",
            sa.Uuid(),
            sa.ForeignKey("order_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "market_code",
            sa.String(length=10),
            sa.ForeignKey("markets.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("object_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
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
            "size_bytes > 0", name="ck_order_item_attachments_size_positive"
        ),
    )
    op.create_index(
        "ix_order_item_attachments_order_item",
        "order_item_attachments",
        ["order_item_id"],
    )
    op.create_index(
        "ix_order_item_attachments_pending_owner",
        "order_item_attachments",
        ["uploaded_by_user_id", "market_code"],
        postgresql_where=sa.text("order_item_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_item_attachments_pending_owner",
        table_name="order_item_attachments",
    )
    op.drop_index(
        "ix_order_item_attachments_order_item",
        table_name="order_item_attachments",
    )
    op.drop_table("order_item_attachments")
