"""R8: UF do Brasil restrita às 27 siglas oficiais no banco

Revision ID: uf_whitelist_r8_20261005
Revises: market_fk_r7_20261005
Create Date: 2026-10-05

`ck_clients_state_uf` e `ck_representatives_state_uf` validavam só o formato
(`market_code <> 'BR' OR state ~ '^[A-Z]{2}$'`), então `state='XX'` entrava no
banco. O servidor passou a conferir a lista em `app/core/addresses.py` (commit
`35389f79`), o que cobre API e importação CSV — mas não uma inserção direta:
migration de dados, SQL manual, script de correção.

Esta revisão move a lista para a constraint, fechando esse caminho. A sentinela
`--` continua aceita fora de BR, como antes.

Padrão de aplicação igual ao da `0033`: `NOT VALID` primeiro, `VALIDATE` depois,
para não travar a tabela durante a verificação das linhas existentes.

A revisão é abortiva: se alguma linha BR tiver UF fora da lista, ela falha
dizendo quantas e em qual tabela, em vez de deixar a constraint inválida.
"""
from alembic import op

from app.core.addresses import BR_STATES, br_uf_check_condition


revision = "uf_whitelist_r8_20261005"
down_revision = "market_fk_r7_20261005"
branch_labels = None
depends_on = None


# A lista vem de app/core/addresses.py, a mesma que os schemas e o importador
# usam. Uma revisão normalmente congela o que leu, para não mudar de efeito se o
# código evoluir; aqui a dependência é deliberada: duas cópias da lista acabariam
# divergindo, e criar unidade federativa é alteração constitucional, não rotina.
_STATE_LIST = ", ".join(f"'{uf}'" for uf in sorted(BR_STATES))
_CONDITION = br_uf_check_condition()

_TABLES = ("clients", "representatives")


def _constraint_name(table: str) -> str:
    return f"ck_{table}_state_uf"


def _assert_no_invalid_uf() -> None:
    conn = op.get_bind()
    offenders = []
    for table in _TABLES:
        count = conn.exec_driver_sql(
            f"SELECT count(*) FROM {table} "  # nome vem de _TABLES, não de entrada
            f"WHERE market_code = 'BR' AND state NOT IN ({_STATE_LIST})"
        ).scalar() or 0
        if count:
            offenders.append(f"{count} linha(s) em {table}")
    if offenders:
        raise RuntimeError(
            "Migration abortada — há registro BR com UF fora das 27 siglas "
            "oficiais. Corrija antes de aplicar a restrição:\n  - "
            + "\n  - ".join(offenders)
        )


def upgrade() -> None:
    _assert_no_invalid_uf()
    for table in _TABLES:
        name = _constraint_name(table)
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK ({_CONDITION}) NOT VALID"
        )
    # Separado do ADD para que a verificação das linhas existentes não segure a
    # tabela no mesmo lock do DDL.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {_constraint_name(table)}")


def downgrade() -> None:
    for table in _TABLES:
        name = _constraint_name(table)
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK (market_code <> 'BR' OR state ~ '^[A-Z]{{2}}$')"
        )
