"""cpf_cnpj em clientes e representantes

A coluna aceita nulo: o campo é opcional por decisão de produto e os cadastros
anteriores a esta migration não têm o dado.

O índice único é criado agora justamente porque ainda não há nenhum valor
gravado — depois, com base preenchida, um duplicado legítimo faria a migration
falhar no deploy. No PostgreSQL nulos não conflitam entre si, então o legado
sem documento convive com a restrição.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_TABLES = ("clients", "representatives")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        columns = {col["name"] for col in inspector.get_columns(table)}
        if "cpf_cnpj" not in columns:
            op.add_column(
                table,
                sa.Column("cpf_cnpj", sa.String(length=14), nullable=True),
            )
        index_name = f"uq_{table}_cpf_cnpj"
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        existing |= {
            c["name"] for c in inspector.get_unique_constraints(table) if c.get("name")
        }
        if index_name not in existing:
            op.create_index(index_name, table, ["cpf_cnpj"], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in _TABLES:
        index_name = f"uq_{table}_cpf_cnpj"
        if index_name in {idx["name"] for idx in inspector.get_indexes(table)}:
            op.drop_index(index_name, table_name=table)
        if "cpf_cnpj" in {col["name"] for col in inspector.get_columns(table)}:
            op.drop_column(table, "cpf_cnpj")
