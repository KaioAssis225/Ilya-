"""Helper de Market e defaults sintéticos para testes de integração.

Os registros Market BR e EU existem via seed das migrations — nunca são
criados aqui. `require_market` busca o registro existente e falha claramente
se a migration não o semeou. `market_defaults` centraliza os valores
sintéticos de endereço/moeda/locale usados pelos builders.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addresses import UF_SENTINEL
from app.models.market import Market

_KNOWN: frozenset[str] = frozenset({"BR", "EU"})

_DEFAULTS: dict[str, dict[str, str | None]] = {
    "BR": {
        "currency": "BRL",
        "country": "BR",
        "state": "SP",
        "cep": "01310-100",
        "city": "São Paulo",
        "locale": "pt-BR",
    },
    "EU": {
        "currency": "EUR",
        "country": "PT",
        "state": UF_SENTINEL,
        "cep": "1234-567",
        "city": "Lisboa",
        "locale": "pt-PT",
    },
}


def market_defaults(market_code: str) -> dict[str, str | None]:
    """Cópia dos defaults sintéticos para market_code.

    Levanta ValueError para código desconhecido — sem fallback silencioso.
    """
    if market_code not in _KNOWN:
        raise ValueError(
            f"market_defaults: código desconhecido {market_code!r}. "
            f"Valores aceitos: {sorted(_KNOWN)}"
        )
    return dict(_DEFAULTS[market_code])


async def require_market(
    db: AsyncSession,
    market_code: str,
    *,
    enabled: bool | None = None,
) -> Market:
    """Busca Market seeded pela migration; falha claramente se não existir.

    Não cria nem duplica registros. Aceita apenas BR e EU. Se `enabled` for
    fornecido, atualiza is_enabled e faz flush (dentro da transação corrente).

    Levanta:
        ValueError      — market_code desconhecido.
        AssertionError  — registro ausente (migration não rodou o seed).
    """
    if market_code not in _KNOWN:
        raise ValueError(
            f"require_market: código desconhecido {market_code!r}. "
            f"Valores aceitos: {sorted(_KNOWN)}"
        )
    market = await db.get(Market, market_code)
    if market is None:
        raise AssertionError(
            f"require_market: Market {market_code!r} não encontrado — "
            "certifique-se de que alembic upgrade head foi executado antes dos testes."
        )
    if enabled is not None and market.is_enabled != enabled:
        market.is_enabled = enabled
        await db.flush()
    return market
