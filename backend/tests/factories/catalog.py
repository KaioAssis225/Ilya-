"""Builders mínimos de catálogo, clientes e representantes para testes de integração."""
import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Catalog
from app.models.market import PriceList
from app.models.client import Client
from app.models.representative import Representative
from tests.factories.markets import market_defaults


async def make_catalog(
    db: AsyncSession,
    *,
    market_code: str,
    name: str | None = None,
) -> Catalog:
    """Cria um Catalog no mercado especificado (unique por market_code+name)."""
    _name = name or f"catalog-{uuid.uuid4().hex[:8]}"
    catalog = Catalog(market_code=market_code, name=_name)
    db.add(catalog)
    await db.flush()
    return catalog


async def make_price_list(
    db: AsyncSession,
    *,
    market_code: str,
    code: str | None = None,
    name: str | None = None,
    currency: str | None = None,
) -> PriceList:
    """Cria uma lista de preço no mercado especificado."""
    _code = code or f"test-{uuid.uuid4().hex[:8]}"
    _currency = currency or market_defaults(market_code)["currency"]
    _name = name or f"{_code}-{market_code}"
    pl = PriceList(
        market_code=market_code,
        code=_code,
        name=_name,
        currency=_currency,
    )
    db.add(pl)
    await db.flush()
    return pl


async def make_client(
    db: AsyncSession,
    price_list: PriceList,
    *,
    market_code: str,
    name: str = "Test Client",
    country: str | None = None,
    state: str | None = None,
) -> Client:
    """Cria um Cliente sintético no mercado especificado."""
    defaults = market_defaults(market_code)
    _country = country or defaults["country"]
    _state = state or defaults["state"]
    client = Client(
        market_code=market_code,
        name=name,
        phone="11999999999",
        cep=defaults["cep"],
        address="Rua Teste, 1",
        city=defaults["city"],
        state=_state,
        country=_country,
        price_list_id=price_list.id,
        price_profile="lojista",
        max_discount=Decimal("0.00"),
    )
    db.add(client)
    await db.flush()
    return client


async def make_representative(
    db: AsyncSession,
    *,
    market_code: str,
    name: str = "Test Rep",
    country: str | None = None,
    state: str | None = None,
) -> Representative:
    """Cria um Representante sintético no mercado especificado."""
    defaults = market_defaults(market_code)
    _country = country or defaults["country"]
    _state = state or defaults["state"]
    rep = Representative(
        market_code=market_code,
        name=name,
        phone="11999999998",
        cep=defaults["cep"],
        address="Rua Teste, 2",
        city=defaults["city"],
        state=_state,
        country=_country,
    )
    db.add(rep)
    await db.flush()
    return rep
