"""Regras de endereço que variam por mercado.

`clients.state` e `representatives.state` são `NOT NULL` no banco, mas unidade
federativa só existe no Brasil. A sentinela abaixo é o valor que atravessa esse
`NOT NULL` quando o mercado não usa UF; quem decide se ela é aceitável é a regra
do mercado, não a coluna:

- em BR, `UF_SENTINEL` é recusada e a sigla precisa constar em `BR_STATES`;
- fora de BR, a sentinela é o valor esperado, e a divisão administrativa
  (distrito, província) vai em `region`.

A lista existe porque a `CheckConstraint ck_clients_state_uf` valida apenas o
formato (`^[A-Z]{2}$`), então `XX` passava pelo banco. Validar no servidor evita
cadastro com UF inexistente sem precisar de migration de constraint.
"""

UF_SENTINEL = "--"

BR_STATES = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})


def is_valid_uf(state: str) -> bool:
    """True para uma das 27 siglas oficiais, já em maiúsculas."""
    return state in BR_STATES
