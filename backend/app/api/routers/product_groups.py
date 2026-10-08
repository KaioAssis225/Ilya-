import uuid
from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_product_group_editor, require_roles
from app.core.fiscal_audit import record_product_group_event
from app.core.markets import BR_MARKET, MarketPrincipal
from app.models.product_group import ProductGroup
from app.models.user import UserRole
from app.schemas.product_group import ProductGroupCreate, ProductGroupUpdate, ProductGroupRead

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
