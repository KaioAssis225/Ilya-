"""Builders mínimos de pedidos para testes de integração (ISO-23)."""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Catalog
from app.models.order import Order
from app.models.client import Client


async def make_order(
    db: AsyncSession,
    client: Client,
    owner_user_id: uuid.UUID,
    *,
    market_code: str | None = None,
    catalog: Catalog | None = None,
) -> Order:
    """Cria um pedido sintético associado ao cliente informado.

    O mercado do pedido é herdado do cliente quando não especificado. Sem
    catálogo, cria um próprio: o campo é obrigatório (catalog_permissions_r21).
    """
    _market = market_code or client.market_code
    if catalog is None:
        catalog = Catalog(market_code=_market, name=f"catalog-{uuid.uuid4().hex[:8]}")
        db.add(catalog)
        await db.flush()
    # Número sequencial fictício — não usa a sequence do banco para evitar
    # colisões com o rollback: o counter de ordem não participa da transação.
    order = Order(
        market_code=_market,
        client_id=client.id,
        catalog_id=catalog.id,
        catalog_name=catalog.name,
        number_owner_id=owner_user_id,
        order_number=1,
        code=f"PED-TEST-{uuid.uuid4().hex[:6].upper()}",
        orc_id=f"ORC-TEST-{uuid.uuid4().hex[:6].upper()}",
        price_list_code="lojista",
        currency="BRL" if _market == "BR" else "EUR",
        locale="pt-BR" if _market == "BR" else "pt-PT",
        total_value=0,
        total_ipi=0,
        total_with_ipi=0,
    )
    db.add(order)
    await db.flush()
    return order
