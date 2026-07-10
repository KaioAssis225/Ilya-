"""add 'cliente' role and reclassify client-portal accounts (SEC-01)

Separa a role de portal do cliente-final da role de operador interno `vendedor`.
Contas de cliente eram criadas com `vendedor` + `linked_id`, o que lhes dava, via
chamada direta à API, acesso a mutações de catálogo. A partir daqui o cliente-final
tem a role própria `cliente`, que não figura em nenhuma permissão administrativa.

Revision ID: 0028
Revises: 7457e87fa461
Create Date: 2026-07-10
"""
from alembic import op

revision = '0028'
down_revision = '7457e87fa461'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE precisa estar commitado antes de ser usado no mesmo
    # migration; autocommit_block sai da transação do Alembic para garantir isso.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'cliente'")

    # Reclassifica apenas contas de portal de CLIENTE (têm linked_id apontando para
    # o próprio cliente). Contas de representante usam role 'representante' e não
    # são tocadas; operadores internos 'vendedor' (sem linked_id) permanecem.
    op.execute(
        "UPDATE users SET role = 'cliente' "
        "WHERE role = 'vendedor' AND linked_id IS NOT NULL"
    )


def downgrade() -> None:
    # Reverte as contas para a role legada antes de qualquer remoção do valor de enum.
    op.execute(
        "UPDATE users SET role = 'vendedor' "
        "WHERE role = 'cliente' AND linked_id IS NOT NULL"
    )
    # PostgreSQL não suporta remover valores de enum — o valor 'cliente' permanece
    # no tipo, porém sem uso após o downgrade.
