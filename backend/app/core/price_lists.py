"""Códigos das tabelas de preço de cada mercado, num lugar só.

Antes, a lista (lojista, corporativo, pvp, arquiteto) estava escrita à mão em
`api/price_access.py`, `api/routers/markets.py` e `api/routers/products.py`.
Aqui ficam o que cada mercado vende e a ordem de exibição; quem precisar de
uma lista importa daqui.

A tabela `price_lists` do banco continua sendo quem diz o que existe de fato
(ativa, moeda). Estes códigos dizem o que o CÓDIGO exige de cada mercado.
"""
from __future__ import annotations

from app.models.market import BR_MARKET, EU_MARKET

# Ordem de exibição de todas as tabelas conhecidas.
PRICE_LIST_ORDER: tuple[str, ...] = ("lojista", "corporativo", "pvp", "arquiteto")

# Tabelas que todo produto ativo precisa ter em cada mercado.
MARKET_PRICE_LISTS: dict[str, tuple[str, ...]] = {
    BR_MARKET: ("lojista", "corporativo"),
    EU_MARKET: ("lojista", "corporativo", "pvp", "arquiteto"),
}

EU_PRICE_LISTS: tuple[str, ...] = MARKET_PRICE_LISTS[EU_MARKET]


def market_price_lists(market_code: str) -> tuple[str, ...]:
    """Tabelas obrigatórias do mercado, na ordem de exibição."""
    return MARKET_PRICE_LISTS[market_code]
