"""Boxes de showroom EU e permissão por vínculo de usuário.

Cria a box inicial "Showroom Portugal", concede a capacidade aos
administradores EU e a james@ibtw.pt e mantém preços como referência viva à
tabela EU, sem duplicar valores monetários.
"""

from alembic import op
import sqlalchemy as sa


revision = "showroom_boxes_r47"
down_revision = "prototype_options_r46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_markets",
        sa.Column(
            "can_manage_showrooms", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_check_constraint(
        "ck_user_markets_showrooms_eu", "user_markets",
        "NOT can_manage_showrooms OR market_code = 'EU'",
    )
    op.execute(sa.text(
        "UPDATE user_markets um SET can_manage_showrooms = true "
        "FROM users u WHERE u.id = um.user_id AND um.market_code = 'EU' "
        "AND um.status = 'active' AND u.is_active "
        "AND (um.role = 'admin' OR lower(u.email) = 'james@ibtw.pt')"
    ))

    op.create_table(
        "showroom_boxes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("market_code", sa.String(2), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price_list_code", sa.String(30), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("market_code = 'EU'", name="ck_showroom_boxes_eu"),
        sa.ForeignKeyConstraint(
            ["market_code", "price_list_code"],
            ["price_lists.market_code", "price_lists.code"],
            name="fk_showroom_boxes_price_list", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            name="fk_showroom_boxes_created_by", ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_showroom_boxes_market_updated", "showroom_boxes",
        ["market_code", "updated_at"],
    )
    op.create_table(
        "showroom_box_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_showroom_box_items_quantity"),
        sa.ForeignKeyConstraint(
            ["box_id"], ["showroom_boxes.id"],
            name="fk_showroom_box_items_box", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            name="fk_showroom_box_items_product", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("box_id", "product_id", name="uq_showroom_box_items_product"),
    )
    op.create_index(
        "ix_showroom_box_items_box", "showroom_box_items",
        ["box_id", "created_at"],
    )
    op.execute(sa.text(
        "INSERT INTO showroom_boxes "
        "(id, market_code, name, price_list_code, created_by_user_id) "
        "SELECT gen_random_uuid(), 'EU', 'Showroom Portugal', 'lojista', "
        "(SELECT um.user_id FROM user_markets um JOIN users u ON u.id = um.user_id "
        " WHERE um.market_code = 'EU' AND um.status = 'active' AND u.is_active "
        " AND (lower(u.email) = 'james@ibtw.pt' OR um.role = 'admin') "
        " ORDER BY CASE WHEN lower(u.email) = 'james@ibtw.pt' THEN 0 "
        "               WHEN um.role = 'admin' THEN 1 ELSE 2 END, um.created_at LIMIT 1) "
        "WHERE EXISTS (SELECT 1 FROM price_lists WHERE market_code = 'EU' AND code = 'lojista') "
        "AND NOT EXISTS (SELECT 1 FROM showroom_boxes WHERE market_code = 'EU' "
        "AND lower(name) = 'showroom portugal')"
    ))


def downgrade() -> None:
    op.drop_index("ix_showroom_box_items_box", table_name="showroom_box_items")
    op.drop_table("showroom_box_items")
    op.drop_index("ix_showroom_boxes_market_updated", table_name="showroom_boxes")
    op.drop_table("showroom_boxes")
    op.drop_constraint("ck_user_markets_showrooms_eu", "user_markets", type_="check")
    op.drop_column("user_markets", "can_manage_showrooms")
