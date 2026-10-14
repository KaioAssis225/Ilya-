"""Independent optional applications and immutable order choice snapshots."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "optional_applications_r18"
down_revision = "eu_architect_price_r17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = postgresql.UUID(as_uuid=True)
    op.create_table(
        "product_optional_applications",
        sa.Column("id", u, primary_key=True),
        sa.Column("product_id", u, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", u, sa.ForeignKey("product_set_components.id", ondelete="CASCADE")),
        sa.Column("category_id", u, sa.ForeignKey("optional_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_en", sa.String(120)),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("allow_all", sa.Boolean(), nullable=False),
        sa.Column("allow_repeat", sa.Boolean(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_optional_application_name"),
        sa.CheckConstraint("display_order >= 0", name="ck_optional_application_order"),
    )
    op.create_index("ix_optional_applications_product", "product_optional_applications", ["product_id", "display_order", "id"])
    op.create_index("ix_optional_applications_component", "product_optional_applications", ["component_id"])
    op.create_table(
        "optional_application_allowed",
        sa.Column("application_id", u, sa.ForeignKey("product_optional_applications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("optional_id", u, sa.ForeignKey("optionals.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_optional_application_allowed_optional", "optional_application_allowed", ["optional_id"])
    op.create_table(
        "order_item_optional_choices",
        sa.Column("id", u, primary_key=True),
        sa.Column("order_item_id", u, sa.ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", u, sa.ForeignKey("product_optional_applications.id", ondelete="SET NULL")),
        sa.Column("optional_id", u, sa.ForeignKey("optionals.id", ondelete="SET NULL")),
        sa.Column("application_name", sa.String(120), nullable=False),
        sa.Column("application_name_en", sa.String(120)),
        sa.Column("category_code", sa.String(50), nullable=False),
        sa.Column("category_name", sa.String(100), nullable=False),
        sa.Column("optional_name", sa.String(100), nullable=False),
        sa.Column("component_name", sa.String(20000)),
        sa.Column("display_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_order_item_optional_choices_item", "order_item_optional_choices", ["order_item_id", "display_order", "id"])
    op.add_column("order_history", sa.Column("items_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_history", "items_snapshot")
    op.drop_index("ix_order_item_optional_choices_item", table_name="order_item_optional_choices")
    op.drop_table("order_item_optional_choices")
    op.drop_index("ix_optional_application_allowed_optional", table_name="optional_application_allowed")
    op.drop_table("optional_application_allowed")
    op.drop_index("ix_optional_applications_component", table_name="product_optional_applications")
    op.drop_index("ix_optional_applications_product", table_name="product_optional_applications")
    op.drop_table("product_optional_applications")
