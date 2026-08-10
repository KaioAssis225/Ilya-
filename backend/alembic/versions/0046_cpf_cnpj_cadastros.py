"""cpf_cnpj em clientes e representantes

A coluna aceita nulo: o campo é opcional por decisão de produto e os cadastros
anteriores a esta migration não têm o dado.

O índice único é criado agora justamente porque ainda não há nenhum valor
gravado — depois, com base preenchida, um duplicado legítimo faria a migration
falhar no deploy. No PostgreSQL nulos não conflitam entre si, então o legado
sem documento convive com a restrição.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_TABLES = ("clients", "representatives")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("cpf_cnpj", sa.String(length=14), nullable=True),
        )
        op.create_index(
            f"uq_{table}_cpf_cnpj",
            table,
            ["cpf_cnpj"],
            unique=True,
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"uq_{table}_cpf_cnpj", table_name=table)
        op.drop_column(table, "cpf_cnpj")
