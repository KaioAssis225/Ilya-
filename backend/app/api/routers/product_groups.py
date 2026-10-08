import uuid
from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_product_group_editor, require_roles
from app.core.fiscal_audit import record_product_group_event
from app.core.markets import BR_MARKET, MarketPrincipal
from app.models.market import VAT_APPROVED, ProductMarket
from app.models.product import Product
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.models.user import UserRole
from app.schemas.product_group import ProductGroupCreate, ProductGroupUpdate, ProductGroupRead, ProductGroupVatSummary

router = APIRouter(prefix="/api/v1/product-groups", tags=["product-groups"])

_ANY = Depends(
    require_roles(
        UserRole.admin,
        UserRole.vendedor,
        UserRole.representante,
        UserRole.cliente,
        UserRole.produtos,
    )
)

# Grupos são por mercado (eu_product_groups_r13_20261008). No Brasil o grupo
# carrega o IPI e toda mudança é auditada como evento fiscal. Em Portugal o
# grupo só organiza o catálogo: IPI é sempre 0 e não há evento fiscal.


def _require_no_ipi_outside_br(principal: MarketPrincipal, ipi: Decimal | None) -> None:
    if principal.code != BR_MARKET and ipi is not None and ipi != 0:
        raise HTTPException(
            status_code=422,
            detail="Grupo fora do Brasil não tem IPI; o imposto do pedido vem do IVA aprovado do produto.",
        )


async def _group_in_market(db: AsyncSession, group_id: uuid.UUID, principal: MarketPrincipal) -> ProductGroup:
    pg = await db.get(ProductGroup, group_id)
    if not pg or pg.market_code != principal.code:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
    return pg


def summarize_group_vat(rows) -> list[ProductGroupVatSummary]:
    """Agrega (group_id, vat_rate, vat_status, n_produtos) por grupo.

    Só taxa com status aprovado conta como IVA do grupo; o resto é pendente.
    """
    by_group: dict[uuid.UUID, dict] = {}
    for group_id, vat_rate, vat_status, count in rows:
        entry = by_group.setdefault(group_id, {"rates": set(), "approved": 0, "pending": 0})
        if vat_status == VAT_APPROVED and vat_rate is not None:
            entry["rates"].add(Decimal(vat_rate))
            entry["approved"] += int(count)
        else:
            entry["pending"] += int(count)
    return [
        ProductGroupVatSummary(
            group_id=group_id,
            approved_rates=sorted(entry["rates"]),
            approved_products=entry["approved"],
            pending_products=entry["pending"],
        )
        for group_id, entry in by_group.items()
    ]


def _type_key(column):
    # Mesma chave do filtro de catálogo (products._normalized_product_type_expression):
    # caixa, espaços e plural simples não separam produto do seu tipo.
    return func.regexp_replace(func.lower(func.btrim(column)), "s$", "")


@router.get("/vat-summary", response_model=List[ProductGroupVatSummary])
async def product_group_vat_summary(
    db: AsyncSession = Depends(get_db_session),
    _=_ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """IVA aprovado dos produtos de cada grupo — só fora do Brasil, só leitura."""
    if principal.code == BR_MARKET:
        return []
    market = principal.code
    rows = (await db.execute(
        select(ProductType.group_id, ProductMarket.vat_rate, ProductMarket.vat_status, func.count(Product.id))
        .select_from(Product)
        .join(ProductType, and_(
            ProductType.market_code == market,
            _type_key(ProductType.name) == _type_key(Product.type),
        ))
        .join(ProductMarket, and_(
            ProductMarket.product_id == Product.id,
            ProductMarket.market_code == market,
        ))
        .where(
            Product.market_code == market,
            Product.is_active.is_(True),
            ProductMarket.is_available.is_(True),
            ProductType.group_id.is_not(None),
        )
        .group_by(ProductType.group_id, ProductMarket.vat_rate, ProductMarket.vat_status)
    )).all()
    return summarize_group_vat(rows)


@router.get("", response_model=List[ProductGroupRead])
async def list_product_groups(
    db: AsyncSession = Depends(get_db_session),
    _=_ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(
        select(ProductGroup)
        .where(ProductGroup.market_code == principal.code)
        .order_by(ProductGroup.name)
    )
    return result.scalars().all()


@router.post("", response_model=ProductGroupRead, status_code=status.HTTP_201_CREATED)
async def create_product_group(
    payload: ProductGroupCreate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(require_product_group_editor),
):
    _require_no_ipi_outside_br(principal, payload.ipi)
    data = payload.model_dump()
    if principal.code != BR_MARKET:
        data["ipi"] = Decimal("0")
    pg = ProductGroup(id=uuid.uuid4(), market_code=principal.code, **data)
    db.add(pg)
    if principal.code == BR_MARKET:
        record_product_group_event(
            db,
            product_group_id=pg.id,
            actor_user_id=principal.user.id,
            market_code=principal.code,
            action="created",
            source="api",
            group_name=pg.name,
            old_ipi=None,
            new_ipi=pg.ipi,
        )
    try:
        await db.commit()
        await db.refresh(pg)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Grupo de produto já existe.")
    return pg


@router.put("/{group_id}", response_model=ProductGroupRead)
async def update_product_group(
    group_id: uuid.UUID,
    payload: ProductGroupUpdate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(require_product_group_editor),
):
    _require_no_ipi_outside_br(principal, payload.ipi)
    pg = await _group_in_market(db, group_id, principal)
    old_ipi = pg.ipi
    if payload.name is not None:
        pg.name = payload.name
    if payload.ipi is not None and principal.code == BR_MARKET:
        pg.ipi = payload.ipi
    if principal.code == BR_MARKET and pg.ipi != old_ipi:
        record_product_group_event(
            db,
            product_group_id=pg.id,
            actor_user_id=principal.user.id,
            market_code=principal.code,
            action="updated",
            source="api",
            group_name=pg.name,
            old_ipi=old_ipi,
            new_ipi=pg.ipi,
        )
    try:
        await db.commit()
        await db.refresh(pg)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Grupo de produto já existe.")
    return pg


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(require_product_group_editor),
):
    pg = await _group_in_market(db, group_id, principal)
    if principal.code == BR_MARKET:
        record_product_group_event(
            db,
            product_group_id=pg.id,
            actor_user_id=principal.user.id,
            market_code=principal.code,
            action="deleted",
            source="api",
            group_name=pg.name,
            old_ipi=pg.ipi,
            new_ipi=None,
        )
    await db.delete(pg)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Grupo em uso por tipo de produto.")
