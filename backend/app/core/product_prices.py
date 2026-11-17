"""Preço de produto: `product_prices` é a fonte do preço.

O pedido sempre cobrou de `product_prices`. As colunas antigas em `products`
(`price`, `price_lojista`, `price_corporativo`) viraram cópia: ainda são
gravadas (um PR futuro para de gravar e outro as retira), mas ninguém deve
LER delas para decidir preço. Este módulo concentra o que os gravadores e os
leitores precisam, para existir uma regra só:

* `set_product_prices` grava (insere ou atualiza) o preço de um produto em
  várias listas. É o único jeito de escrever em `product_prices`;
* `price_sort_expression` ordena o catálogo pelo preço de uma lista;
* `get_list_price` lê o preço de um produto em uma lista.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import PriceList, ProductPrice
from app.models.product import Product


async def load_price_lists(
    db: AsyncSession, market_code: str, *, active_only: bool = True
) -> dict[str, PriceList]:
    """Tabelas de preço do mercado, indexadas pelo código."""
    stmt = select(PriceList).where(PriceList.market_code == market_code)
    if active_only:
        stmt = stmt.where(PriceList.is_active.is_(True))
    return {item.code: item for item in (await db.execute(stmt)).scalars().all()}


async def set_product_prices(
    db: AsyncSession,
    product_id: uuid.UUID,
    price_lists: Mapping[str, PriceList],
    amounts: Mapping[str, Decimal | None],
) -> int:
    """Grava o preço do produto em cada lista de `amounts`.

    Valor `None` é ignorado (não apaga o preço existente). Código sem lista em
    `price_lists` é erro de quem chamou: levanta `ValueError` em vez de pular
    em silêncio. O produto precisa já existir no banco (`flush` antes).
    Devolve quantas listas foram gravadas.
    """
    written = 0
    for code, amount in amounts.items():
        if amount is None:
            continue
        price_list = price_lists.get(code)
        if price_list is None:
            raise ValueError(f"Tabela de preço '{code}' não existe no mercado.")
        stmt = pg_insert(ProductPrice).values(
            product_id=product_id, price_list_id=price_list.id, amount=amount
        )
        await db.execute(stmt.on_conflict_do_update(
            index_elements=[ProductPrice.product_id, ProductPrice.price_list_id],
            set_={"amount": stmt.excluded.amount, "updated_at": func.now()},
        ))
        written += 1
    return written


def price_sort_expression(market_code: str, list_code: str):
    """Preço do produto na lista, para `ORDER BY` (sem preço conta como 0).

    Substitui a ordenação pelas colunas antigas de `products`, que ficavam
    velhas depois de uma importação de preços.
    """
    amount = (
        select(ProductPrice.amount)
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .where(
            ProductPrice.product_id == Product.id,
            PriceList.market_code == market_code,
            PriceList.code == list_code,
        )
        .correlate(Product)
        .scalar_subquery()
    )
    return func.coalesce(amount, 0)


async def get_list_price(
    db: AsyncSession, product_id: uuid.UUID, market_code: str, list_code: str
) -> Decimal | None:
    """Preço do produto na lista do mercado, ou None se não houver."""
    return (await db.execute(
        select(ProductPrice.amount)
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .where(
            ProductPrice.product_id == product_id,
            PriceList.market_code == market_code,
            PriceList.code == list_code,
        )
    )).scalar_one_or_none()
