"""Integração Moloni: OAuth cifrado e fila idempotente de orçamentos EU.

Revision ID: moloni_integration_r14_20261009
Revises: eu_product_groups_r13_20261008
"""
import sqlalchemy as sa
from alembic import op

revision = "moloni_integration_r14_20261009"
down_revision = "eu_product_groups_r13_20261008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("moloni_connections",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False), sa.Column("refresh_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)), sa.Column("connected_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("moloni_oauth_states",
        sa.Column("state", sa.String(128), primary_key=True), sa.Column("company_id", sa.Integer(), nullable=False), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used_at", sa.DateTime(timezone=True)))
    op.create_table("moloni_tax_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("moloni_connections.id", ondelete="CASCADE"), nullable=False), sa.Column("vat_rate", sa.Numeric(5,2), nullable=False), sa.Column("moloni_tax_id", sa.Integer(), nullable=False), sa.UniqueConstraint("connection_id", "vat_rate", name="uq_moloni_tax_connection_rate"))
    op.create_table("moloni_export_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("next_attempt_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.Text()), sa.Column("moloni_document_id", sa.Integer(), unique=True), sa.Column("delivered_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("order_id", name="uq_moloni_export_jobs_order"), sa.CheckConstraint("status IN ('pending', 'processing', 'delivered', 'dead_letter')", name="ck_moloni_export_job_status"))
    op.create_index("ix_moloni_export_jobs_status_next", "moloni_export_jobs", ["status", "next_attempt_at"])
    op.create_table("moloni_customer_links", sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("moloni_connections.id", ondelete="CASCADE"), primary_key=True), sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="RESTRICT"), primary_key=True), sa.Column("moloni_customer_id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("moloni_product_links", sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("moloni_connections.id", ondelete="CASCADE"), primary_key=True), sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True), sa.Column("moloni_product_id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade() -> None:
    op.drop_index("ix_moloni_export_jobs_status_next", table_name="moloni_export_jobs")
    op.drop_table("moloni_product_links"); op.drop_table("moloni_customer_links"); op.drop_table("moloni_export_jobs"); op.drop_table("moloni_tax_mappings"); op.drop_table("moloni_oauth_states"); op.drop_table("moloni_connections")
