"""IVA único do mercado EU (Portugal): taxa configurável aplicada só no total.

O IVA português é cobrado uma vez, sobre o total do documento (subtotal já com
descontos) — não por produto, como o ICMS. A taxa vive em `markets.vat_rate`;
cada pedido grava a taxa usada em `orders.vat_rate` (snapshot).

Arredondamento: o IVA é calculado na base total, `round_half_up(subtotal × taxa
/ 100, 2)`, e não linha a linha. As linhas continuam arredondadas a 2 casas
como sempre; o IVA do documento é um único arredondamento sobre a soma delas.
"""
import uuid
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import EU_MARKET, Market, MarketVatRateEvent

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


def total_vat(subtotal: Decimal, rate: Decimal, *, exempt: bool = False) -> Decimal:
    """IVA do documento sobre o subtotal; isento é sempre zero."""
    if exempt:
        return Decimal("0.00")
    return (Decimal(subtotal) * Decimal(rate) / _HUNDRED).quantize(_CENT, rounding=ROUND_HALF_UP)


def normalize_vat_rate(value: Decimal) -> Decimal:
    """Taxa válida: entre 0 e 100, no máximo duas casas decimais."""
    rate = Decimal(value)
    if not rate.is_finite() or rate < 0 or rate > _HUNDRED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A taxa de IVA deve estar entre 0 e 100.",
        )
    if rate != rate.quantize(_CENT):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A taxa de IVA aceita no máximo duas casas decimais.",
        )
    return rate.quantize(_CENT)


async def load_eu_vat_rate(db: AsyncSession) -> Decimal:
    """Taxa única vigente. Sem taxa configurada o pedido não é emitido: nunca
    se inventa 0% (que faturaria sem IVA em silêncio)."""
    rate = (await db.execute(
        select(Market.vat_rate).where(Market.code == EU_MARKET)
    )).scalar_one_or_none()
    if rate is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A taxa de IVA do mercado europeu não está configurada.",
        )
    return Decimal(rate)


async def set_eu_vat_rate(
    db: AsyncSession, new_rate: Decimal, actor_user_id: uuid.UUID
) -> tuple[Decimal | None, Decimal]:
    """Grava a taxa e registra a mudança (quem, quando, valor antigo e novo).

    Devolve (antiga, nova). Repetir o valor atual não gera evento. Não confirma
    a transação: quem chama faz o commit.
    """
    new_rate = normalize_vat_rate(new_rate)
    market = (await db.execute(
        select(Market).where(Market.code == EU_MARKET).with_for_update()
    )).scalar_one_or_none()
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mercado europeu não encontrado.")
    old_rate = market.vat_rate
    if old_rate is not None and Decimal(old_rate) == new_rate:
        return Decimal(old_rate), new_rate
    market.vat_rate = new_rate
    db.add(MarketVatRateEvent(
        id=uuid.uuid4(),
        market_code=EU_MARKET,
        actor_user_id=actor_user_id,
        old_rate=old_rate,
        new_rate=new_rate,
    ))
    return (Decimal(old_rate) if old_rate is not None else None), new_rate
