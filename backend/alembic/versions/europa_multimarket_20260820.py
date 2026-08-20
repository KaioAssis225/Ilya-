"""estrutura multimercado Brasil/Europa

Revision ID: europa_multimarket_20260820
Revises: 0050
Create Date: 2026-08-20

Expansão segura: todo o legado é classificado como BR. A Europa nasce
desabilitada e só pode ser ativada depois da importação validada.
"""
from alembic import op
import sqlalchemy as sa


revision = "europa_multimarket_20260820"
down_revision = "0050"
branch_labels = None
depends_on = None

BR_LOJISTA = "b1000000-0000-0000-0000-000000000001"
BR_CORPORATIVO = "b1000000-0000-0000-0000-000000000002"
EU_LOJISTA = "e1000000-0000-0000-0000-000000000001"
EU_CORPORATIVO = "e1000000-0000-0000-0000-000000000002"
EU_PVP = "e1000000-0000-0000-0000-000000000003"


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("code", sa.String(2), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("tax_label", sa.String(10), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("""
        INSERT INTO markets (code,name,currency,locale,tax_label,is_enabled) VALUES
        ('BR','Brasil','BRL','pt-BR','IPI',true),
        ('EU','Europa','EUR','pt-PT','IVA',false)
    """)
    op.create_table(
        "price_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("market_code", "code", name="uq_price_lists_market_code"),
    )
    op.create_index("ix_price_lists_market_active", "price_lists", ["market_code", "is_active"])
    op.execute(f"""
        INSERT INTO price_lists (id,market_code,code,name,currency) VALUES
        ('{BR_LOJISTA}','BR','lojista','Lojista','BRL'),
        ('{BR_CORPORATIVO}','BR','corporativo','Corporativo','BRL'),
        ('{EU_LOJISTA}','EU','lojista','Lojista','EUR'),
        ('{EU_CORPORATIVO}','EU','corporativo','Corporativo','EUR'),
        ('{EU_PVP}','EU','pvp','PVP','EUR')
    """)

    op.add_column("users", sa.Column("home_market", sa.String(2), nullable=True))
    op.create_foreign_key("fk_users_home_market", "users", "markets", ["home_market"], ["code"])
    op.execute("UPDATE users SET home_market='BR'")
    op.alter_column("users", "home_market", nullable=False, server_default="BR")
    op.create_table(
        "user_markets",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("INSERT INTO user_markets (user_id,market_code) SELECT id,'BR' FROM users")
    op.execute("INSERT INTO user_markets (user_id,market_code) SELECT id,'EU' FROM users WHERE role='admin'")
    op.create_table(
        "market_order_counters",
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code"), primary_key=True),
        sa.Column("number_owner_id", sa.Uuid(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("next_value > 0", name="ck_market_order_counters_positive"),
    )
    op.execute("INSERT INTO market_order_counters (market_code,number_owner_id,next_value) SELECT 'BR',number_owner_id,next_value FROM order_number_counters")
    op.create_table(
        "market_quote_counters",
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code"), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("next_value > 0", name="ck_market_quote_counters_positive"),
    )
    op.execute("INSERT INTO market_quote_counters (market_code,next_value) VALUES ('BR', nextval('order_seq')), ('EU', 1)")

    op.add_column("refresh_tokens", sa.Column("active_market", sa.String(2), nullable=True))
    op.create_foreign_key("fk_refresh_tokens_market", "refresh_tokens", "markets", ["active_market"], ["code"])
    op.execute("UPDATE refresh_tokens SET active_market='BR'")
    op.alter_column("refresh_tokens", "active_market", nullable=False, server_default="BR")

    for table in ("clients", "representatives", "orders", "notifications"):
        op.add_column(table, sa.Column("market_code", sa.String(2), nullable=True))
        op.create_foreign_key(f"fk_{table}_market", table, "markets", ["market_code"], ["code"])
        op.execute(f"UPDATE {table} SET market_code='BR'")
        op.alter_column(table, "market_code", nullable=False, server_default="BR")

    op.create_index("ix_clients_market_id", "clients", ["market_code", "id"])
    op.create_index("ix_representatives_market_id", "representatives", ["market_code", "id"])
    op.create_index("ix_orders_market_created_id", "orders", ["market_code", "created_at", "id"])
    op.drop_constraint("uq_orders_number_owner_order_number", "orders", type_="unique")
    op.create_unique_constraint("uq_orders_market_owner_order_number", "orders", ["market_code", "number_owner_id", "order_number"])
    op.create_index("ix_notifications_market_user_created", "notifications", ["market_code", "user_id", "created_at"])
    for table in ("clients", "representatives"):
        op.drop_index(f"uq_{table}_email_lower", table_name=table)
        op.drop_index(f"uq_{table}_cpf_cnpj", table_name=table)
        op.execute(f"CREATE UNIQUE INDEX uq_{table}_market_email_lower ON {table} (market_code, lower(email))")
        op.create_index(f"uq_{table}_market_cpf_cnpj", table, ["market_code", "cpf_cnpj"], unique=True)

    for table in ("clients", "representatives"):
        op.add_column(table, sa.Column("country", sa.String(2), nullable=False, server_default="BR"))
        op.add_column(table, sa.Column("region", sa.String(120), nullable=True))
        op.add_column(table, sa.Column("tax_id", sa.String(40), nullable=True))
    op.drop_constraint("ck_clients_state_uf", "clients", type_="check")
    op.create_check_constraint("ck_clients_state_uf", "clients", "market_code <> 'BR' OR state ~ '^[A-Z]{2}$'")
    op.drop_constraint("ck_representatives_state_uf", "representatives", type_="check")
    op.create_check_constraint("ck_representatives_state_uf", "representatives", "market_code <> 'BR' OR state ~ '^[A-Z]{2}$'")
    op.add_column("clients", sa.Column("price_list_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_clients_price_list", "clients", "price_lists", ["price_list_id"], ["id"])
    op.execute(f"UPDATE clients SET price_list_id=CASE WHEN price_profile='corporativo' THEN '{BR_CORPORATIVO}'::uuid ELSE '{BR_LOJISTA}'::uuid END")
    op.alter_column("clients", "price_list_id", nullable=False)

    op.add_column("orders", sa.Column("price_list_code", sa.String(30), nullable=False, server_default="lojista"))
    op.add_column("orders", sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"))
    op.add_column("orders", sa.Column("locale", sa.String(10), nullable=False, server_default="pt-BR"))
    op.execute("UPDATE orders o SET price_list_code=c.price_profile FROM clients c WHERE c.id=o.client_id")
    op.drop_constraint("orders_orc_id_key", "orders", type_="unique")
    op.create_unique_constraint("uq_orders_market_orc_id", "orders", ["market_code", "orc_id"])
    op.add_column("order_items", sa.Column("tax_label", sa.String(10), nullable=False, server_default="IPI"))
    op.add_column("order_items", sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"))

    op.create_table(
        "product_markets",
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("vat_rate", sa.Numeric(5,2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)", name="ck_product_markets_vat"),
    )
    op.create_index("ix_product_markets_market_available", "product_markets", ["market_code", "is_available"])
    op.execute("INSERT INTO product_markets (product_id,market_code,is_available) SELECT id,'BR',is_active FROM products")
    op.create_table(
        "product_prices",
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("price_list_id", sa.Uuid(), sa.ForeignKey("price_lists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("amount", sa.Numeric(20,2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_product_prices_non_negative"),
    )
    op.create_index("ix_product_prices_list_product", "product_prices", ["price_list_id", "product_id"])
    op.execute(f"INSERT INTO product_prices (product_id,price_list_id,amount) SELECT id,'{BR_LOJISTA}'::uuid,price_lojista FROM products")
    op.execute(f"INSERT INTO product_prices (product_id,price_list_id,amount) SELECT id,'{BR_CORPORATIVO}'::uuid,price_corporativo FROM products")
    op.create_table(
        "market_tax_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("market_code", sa.String(2), sa.ForeignKey("markets.code"), nullable=False),
        sa.Column("product_type", sa.String(80), nullable=False),
        sa.Column("rate", sa.Numeric(5,2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rate >= 0 AND rate <= 100", name="ck_market_tax_rates_range"),
        sa.UniqueConstraint("market_code", "product_type", name="uq_market_tax_rates_market_type"),
    )


def downgrade() -> None:
    op.drop_table("market_tax_rates")
    op.drop_index("ix_product_prices_list_product", table_name="product_prices")
    op.drop_table("product_prices")
    op.drop_index("ix_product_markets_market_available", table_name="product_markets")
    op.drop_table("product_markets")
    op.drop_column("order_items", "currency")
    op.drop_column("order_items", "tax_label")
    op.drop_constraint("uq_orders_market_orc_id", "orders", type_="unique")
    op.create_unique_constraint("orders_orc_id_key", "orders", ["orc_id"])
    for column in ("locale", "currency", "price_list_code"):
        op.drop_column("orders", column)
    op.drop_constraint("fk_clients_price_list", "clients", type_="foreignkey")
    op.drop_column("clients", "price_list_id")
    for table in ("clients", "representatives"):
        for column in ("tax_id", "region", "country"):
            op.drop_column(table, column)
    op.drop_constraint("ck_clients_state_uf", "clients", type_="check")
    op.create_check_constraint("ck_clients_state_uf", "clients", "state ~ '^[A-Z]{2}$'")
    op.drop_constraint("ck_representatives_state_uf", "representatives", type_="check")
    op.create_check_constraint("ck_representatives_state_uf", "representatives", "state ~ '^[A-Z]{2}$'")
    for table, index in (("notifications","ix_notifications_market_user_created"),("orders","ix_orders_market_created_id"),("representatives","ix_representatives_market_id"),("clients","ix_clients_market_id")):
        if table == "orders":
            op.drop_constraint("uq_orders_market_owner_order_number", "orders", type_="unique")
            op.create_unique_constraint("uq_orders_number_owner_order_number", "orders", ["number_owner_id", "order_number"])
        op.drop_index(index, table_name=table)
        op.drop_constraint(f"fk_{table}_market", table, type_="foreignkey")
        if table in ("clients", "representatives"):
            op.drop_index(f"uq_{table}_market_email_lower", table_name=table)
            op.drop_index(f"uq_{table}_market_cpf_cnpj", table_name=table)
        op.drop_column(table, "market_code")
        if table in ("clients", "representatives"):
            op.execute(f"CREATE UNIQUE INDEX uq_{table}_email_lower ON {table} (lower(email))")
            op.create_index(f"uq_{table}_cpf_cnpj", table, ["cpf_cnpj"], unique=True)
    op.drop_constraint("fk_refresh_tokens_market", "refresh_tokens", type_="foreignkey")
    op.drop_column("refresh_tokens", "active_market")
    op.drop_table("user_markets")
    op.drop_table("market_quote_counters")
    op.drop_table("market_order_counters")
    op.drop_constraint("fk_users_home_market", "users", type_="foreignkey")
    op.drop_column("users", "home_market")
    op.drop_index("ix_price_lists_market_active", table_name="price_lists")
    op.drop_table("price_lists")
    op.drop_table("markets")
