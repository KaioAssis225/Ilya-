"""repair integrity, numbering and performance defects from the bug audit

Revision ID: bug_audit_r14_20261008
Revises: eu_product_groups_r13_20261008
"""

from alembic import op
import sqlalchemy as sa


revision = "bug_audit_r14_20261008"
down_revision = "eu_product_groups_r13_20261008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Invitations and signature evidence must never point at nonexistent rows.
    op.execute("DELETE FROM client_access_invitations i WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id=i.user_id) OR NOT EXISTS (SELECT 1 FROM clients c WHERE c.id=i.client_id)")
    for column in ("issued_by_user_id", "requested_by_user_id", "verified_by_user_id"):
        op.execute(sa.text(f"UPDATE client_access_invitations i SET {column}=NULL WHERE {column} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id=i.{column})"))
    op.alter_column("client_access_invitations", "issued_by_user_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("client_access_invitations", "verified_by_user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key("fk_client_access_invitations_user", "client_access_invitations", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_client_access_invitations_client", "client_access_invitations", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_client_access_invitations_issued_by", "client_access_invitations", "users", ["issued_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_client_access_invitations_requested_by", "client_access_invitations", "users", ["requested_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_client_access_invitations_verified_by", "client_access_invitations", "users", ["verified_by_user_id"], ["id"], ondelete="SET NULL")

    op.execute("UPDATE order_signature_evidence e SET submitted_by_user_id=NULL WHERE submitted_by_user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id=e.submitted_by_user_id)")
    op.execute("UPDATE order_signature_evidence e SET invitation_id=NULL WHERE invitation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM signature_invitations i WHERE i.id=e.invitation_id)")
    op.create_foreign_key("fk_order_signature_evidence_submitted_by", "order_signature_evidence", "users", ["submitted_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_order_signature_evidence_invitation", "order_signature_evidence", "signature_invitations", ["invitation_id"], ["id"], ondelete="SET NULL")
    op.add_column(
        "order_signature_evidence",
        sa.Column("hash_version", sa.Integer(), server_default="1", nullable=False),
    )
    # Convites emitidos com a fórmula anterior não podem atravessar o deploy.
    op.execute(
        "UPDATE signature_invitations SET revoked_at=NOW() "
        "WHERE consumed_at IS NULL AND revoked_at IS NULL"
    )

    op.drop_constraint("order_items_order_id_fkey", "order_items", type_="foreignkey")
    op.create_foreign_key("order_items_order_id_fkey", "order_items", "orders", ["order_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("product_set_items_product_id_fkey", "product_set_items", type_="foreignkey")
    op.create_foreign_key("product_set_items_product_id_fkey", "product_set_items", "products", ["product_id"], ["id"], ondelete="CASCADE")

    for table in ("product_set_items", "product_set_components"):
        for column in ("created_at", "updated_at"):
            op.execute(sa.text(f"UPDATE {table} SET {column}=NOW() WHERE {column} IS NULL"))
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                nullable=False,
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )

    op.add_column("orders", sa.Column("is_superseded", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY market_code, code ORDER BY created_at, id) AS rn
            FROM orders
        )
        UPDATE orders o
        SET code = LEFT(o.code, 40) || '-' || SUBSTRING(REPLACE(o.id::text, '-', ''), 1, 8)
        FROM ranked r
        WHERE o.id = r.id AND r.rn > 1
    """)
    op.create_unique_constraint("uq_orders_market_code", "orders", ["market_code", "code"])

    op.execute("UPDATE orders o SET number_owner_id=NULL WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.id=o.number_owner_id)")
    op.alter_column("orders", "number_owner_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key("fk_orders_number_owner_user", "orders", "users", ["number_owner_id"], ["id"], ondelete="SET NULL")

    op.rename_table("market_order_counters", "market_order_counters_per_user")
    op.create_table(
        "market_order_counters",
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("next_value > 0", name="ck_market_order_counters_positive"),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("market_code"),
    )
    op.execute("""
        INSERT INTO market_order_counters (market_code, next_value)
        SELECT m.code, GREATEST(
            COALESCE((SELECT MAX(c.next_value) FROM market_order_counters_per_user c WHERE c.market_code=m.code), 1),
            COALESCE((SELECT MAX(o.order_number) + 1 FROM orders o WHERE o.market_code=m.code), 1)
        )
        FROM markets m
    """)
    op.drop_table("market_order_counters_per_user")
    op.execute("DROP TABLE IF EXISTS order_number_counters")

    indexes = (
        ("ix_orders_supersedes_order_id", "orders", "supersedes_order_id"),
        ("ix_clients_price_list_id", "clients", "price_list_id"),
        ("ix_catalogs_market_code", "catalogs", "market_code"),
        ("ix_user_markets_rep_id", "user_markets", "rep_id"),
        ("ix_user_markets_linked_client_id", "user_markets", "linked_client_id"),
        ("ix_privacy_incidents_updated_by_user_id", "privacy_incidents", "updated_by_user_id"),
        ("ix_product_markets_approved_by_user_id", "product_markets", "approved_by_user_id"),
        ("ix_retention_reviews_created_by_user_id", "retention_reviews", "created_by_user_id"),
        ("ix_retention_reviews_approved_by_user_id", "retention_reviews", "approved_by_user_id"),
        ("ix_legal_holds_created_by_user_id", "legal_holds", "created_by_user_id"),
        ("ix_legal_holds_released_by_user_id", "legal_holds", "released_by_user_id"),
    )
    for name, table, column in indexes:
        op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"))


def downgrade() -> None:
    indexes = (
        ("ix_legal_holds_released_by_user_id", "legal_holds"),
        ("ix_legal_holds_created_by_user_id", "legal_holds"),
        ("ix_retention_reviews_approved_by_user_id", "retention_reviews"),
        ("ix_retention_reviews_created_by_user_id", "retention_reviews"),
        ("ix_product_markets_approved_by_user_id", "product_markets"),
        ("ix_privacy_incidents_updated_by_user_id", "privacy_incidents"),
        ("ix_user_markets_linked_client_id", "user_markets"),
        ("ix_user_markets_rep_id", "user_markets"),
        ("ix_catalogs_market_code", "catalogs"),
        ("ix_clients_price_list_id", "clients"),
        ("ix_orders_supersedes_order_id", "orders"),
    )
    for name, table in indexes:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))

    op.rename_table("market_order_counters", "market_order_counters_global_r14")
    op.create_table(
        "market_order_counters",
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("number_owner_id", sa.Uuid(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("next_value > 0", name="ck_market_order_counters_positive"),
        sa.ForeignKeyConstraint(["market_code"], ["markets.code"]),
        sa.PrimaryKeyConstraint("market_code", "number_owner_id"),
    )
    op.execute("""
        INSERT INTO market_order_counters (market_code, number_owner_id, next_value)
        SELECT market_code, number_owner_id, MAX(order_number) + 1
        FROM orders
        WHERE number_owner_id IS NOT NULL
        GROUP BY market_code, number_owner_id
    """)
    op.drop_table("market_order_counters_global_r14")

    op.create_table(
        "order_number_counters",
        sa.Column("number_owner_id", sa.Uuid(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "next_value > 0", name="ck_order_number_counters_next_value_positive"
        ),
        sa.PrimaryKeyConstraint("number_owner_id", name="pk_order_number_counters"),
    )
    op.execute("""
        INSERT INTO order_number_counters (number_owner_id, next_value)
        SELECT number_owner_id, MAX(order_number) + 1
        FROM orders
        WHERE number_owner_id IS NOT NULL
        GROUP BY number_owner_id
    """)

    op.drop_constraint("fk_orders_number_owner_user", "orders", type_="foreignkey")
    op.alter_column(
        "orders", "number_owner_id", existing_type=sa.Uuid(), nullable=False
    )
    op.drop_constraint("uq_orders_market_code", "orders", type_="unique")
    op.drop_column("orders", "is_superseded")

    for table in ("product_set_components", "product_set_items"):
        for column in ("updated_at", "created_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                nullable=True,
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )

    op.drop_constraint("product_set_items_product_id_fkey", "product_set_items", type_="foreignkey")
    op.create_foreign_key(
        "product_set_items_product_id_fkey",
        "product_set_items",
        "products",
        ["product_id"],
        ["id"],
    )
    op.drop_constraint("order_items_order_id_fkey", "order_items", type_="foreignkey")
    op.create_foreign_key(
        "order_items_order_id_fkey", "order_items", "orders", ["order_id"], ["id"]
    )

    op.drop_column("order_signature_evidence", "hash_version")
    op.drop_constraint(
        "fk_order_signature_evidence_invitation",
        "order_signature_evidence",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_order_signature_evidence_submitted_by",
        "order_signature_evidence",
        type_="foreignkey",
    )
    for name in (
        "fk_client_access_invitations_verified_by",
        "fk_client_access_invitations_requested_by",
        "fk_client_access_invitations_issued_by",
        "fk_client_access_invitations_client",
        "fk_client_access_invitations_user",
    ):
        op.drop_constraint(name, "client_access_invitations", type_="foreignkey")
    op.alter_column(
        "client_access_invitations",
        "verified_by_user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "client_access_invitations",
        "issued_by_user_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
