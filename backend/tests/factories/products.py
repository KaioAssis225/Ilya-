"""Builders mínimos de produto e dimensões para testes de integração (Bloco 1).

Builders reutilizáveis. Sem factory_boy. Respeitam constraints do banco:
- ProductGroup: EU exige ipi=0 (ck_product_groups_eu_sem_ipi)
- Product: product_code único por mercado (uq_products_market_code)
- ProductMarket: vat_status=pending quando approved_*=NULL
"""
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Catalog
from app.models.market import PriceList, ProductMarket, ProductPrice, VAT_PENDING
from app.models.product import Product
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType


async def make_product_group(
    db: AsyncSession,
    *,
    market_code: str,
    name: str | None = None,
    ipi: Decimal = Decimal("0"),
) -> ProductGroup:
    """Cria um ProductGroup (IPI=0 obrigatório para EU)."""
    _name = name or f"group-{uuid.uuid4().hex[:8]}"
    pg = ProductGroup(
        market_code=market_code,
        name=_name,
        ipi=Decimal("0") if market_code != "BR" else ipi,
    )
    db.add(pg)
    await db.flush()
    return pg


async def make_product_type(
    db: AsyncSession,
    *,
    market_code: str,
    name: str | None = None,
    group: ProductGroup | None = None,
) -> ProductType:
    """Cria um ProductType, opcionalmente vinculado a um ProductGroup do mesmo mercado."""
    _name = name or f"type-{uuid.uuid4().hex[:8]}"
    pt = ProductType(
        market_code=market_code,
        name=_name,
        group_id=group.id if group else None,
    )
    db.add(pt)
    await db.flush()
    return pt


async def make_product(
    db: AsyncSession,
    *,
    market_code: str,
    product_code: str | None = None,
    description: str = "Produto Teste",
    catalog: Catalog | None = None,
    price: Decimal = Decimal("0"),
    price_lojista: Decimal = Decimal("0"),
) -> Product:
    """Cria um Product sintético no mercado especificado.

    product_code único por mercado — usa UUID suffix para evitar colisão.
    catalog deve ser do mesmo market_code (FK composta verificada no banco);
    ausente, cria um catálogo próprio, porque o campo é obrigatório (r21).
    """
    _code = product_code or f"TST-{uuid.uuid4().hex[:8].upper()}"
    if catalog is None:
        catalog = Catalog(market_code=market_code, name=f"catalog-{uuid.uuid4().hex[:8]}")
        db.add(catalog)
        await db.flush()
    product = Product(
        market_code=market_code,
        product_code=_code,
        description=description,
        type="Outro",
        catalog_id=catalog.id,
        altura=Decimal("0"),
        largura=Decimal("0"),
        profundidade=Decimal("0"),
        price=price,
        price_lojista=price_lojista,
        price_corporativo=Decimal("0"),
        custo_desativado=Decimal("0"),
        source_version=1,
        is_active=True,
    )
    db.add(product)
    await db.flush()
    return product


async def make_product_market(
    db: AsyncSession,
    product: Product,
    *,
    is_available: bool = True,
    vat_rate: Decimal | None = None,
) -> ProductMarket:
    """Cria entrada ProductMarket (disponibilidade + IVA) para o produto.

    VAT começa pending (approved_* NULL): satisfaz ck_product_markets_vat_approval.
    """
    pm = ProductMarket(
        product_id=product.id,
        market_code=product.market_code,
        is_available=is_available,
        vat_rate=vat_rate,
        vat_status=VAT_PENDING,
        vat_source="import",
        approved_by_user_id=None,
        approved_at=None,
    )
    db.add(pm)
    await db.flush()
    return pm


async def make_product_price(
    db: AsyncSession,
    product: Product,
    price_list: PriceList,
    *,
    amount: Decimal = Decimal("0"),
) -> ProductPrice:
    """Cria uma entrada de preço (product × price_list)."""
    pp = ProductPrice(
        product_id=product.id,
        price_list_id=price_list.id,
        amount=amount,
    )
    db.add(pp)
    await db.flush()
    return pp
