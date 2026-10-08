import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_br_fiscal_admin, require_platform_capability, require_roles
from app.core.fiscal_audit import group_ipi, record_product_type_fiscal_event
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.product_type import ProductTypeCreate, ProductTypeUpdate, ProductTypeRead

router = APIRouter(prefix="/api/v1/product-types", tags=["product-types"])

_ANY = Depends(
    require_roles(
        UserRole.admin,
        UserRole.vendedor,
        UserRole.representante,
        UserRole.cliente,
        UserRole.produtos,
    )
)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.produtos))
_ADMIN = Depends(require_roles(UserRole.admin, UserRole.produtos))


async def _require_group_in_market(db: AsyncSession, group_id: uuid.UUID | None, market_code: str) -> None:
    """Tipo fora do Brasil só entra em grupo do próprio mercado (sem IPI).

    O Brasil continua validando pelo IPI do grupo (group_ipi); a FK composta
    `fk_product_types_group_same_market` repete a regra no banco.
    """
    if group_id is None:
        return
    group = await db.get(ProductGroup, group_id)
    if group is None or group.market_code != market_code:
        raise HTTPException(status_code=422, detail="Grupo não encontrado neste mercado.")


@router.get("", response_model=List[ProductTypeRead])
async def list_product_types(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(ProductType).where(
        ProductType.market_code == principal.code
    ).order_by(ProductType.name))
    return result.scalars().all()


@router.post("", response_model=ProductTypeRead, status_code=status.HTTP_201_CREATED)
async def create_product_type(
    payload: ProductTypeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.code == "BR":
        require_br_fiscal_admin(principal)
    data = payload.model_dump()
    if principal.code != "BR":
        await _require_group_in_market(db, data.get("group_id"), principal.code)
    new_ipi = await group_ipi(db, data.get("group_id")) if principal.code == "BR" else None
    if principal.code == "BR" and data.get("group_id") is not None and new_ipi is None:
        raise HTTPException(status_code=422, detail="Grupo fiscal BR não encontrado.")
    pt = ProductType(id=uuid.uuid4(), market_code=principal.code, **data)
    db.add(pt)
    if principal.code == "BR":
        record_product_type_fiscal_event(
            db, product_type_id=pt.id, actor_user_id=principal.user.id,
            market_code=principal.code, action="created", source="api",
            old_name=None, new_name=pt.name, old_group_id=None,
            new_group_id=pt.group_id, old_ipi=None,
            new_ipi=new_ipi,
        )
    try:
        await db.commit()
        await db.refresh(pt)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tipo de móvel já existe.")
    return pt


@router.get("/platform/EU", response_model=List[ProductTypeRead])
async def list_europe_product_types_before_activation(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    return (await db.execute(select(ProductType).where(
        ProductType.market_code == "EU"
    ).order_by(ProductType.name).execution_options(skip_market_scope=True))).scalars().all()


@router.post("/platform/EU", response_model=ProductTypeRead, status_code=status.HTTP_201_CREATED)
async def create_europe_product_type_before_activation(
    payload: ProductTypeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    await _require_group_in_market(db, payload.group_id, "EU")
    product_type = ProductType(market_code="EU", **payload.model_dump())
    db.add(product_type)
    try:
        await db.commit()
        await db.refresh(product_type)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tipo já existe no mercado EU.")
    return product_type


@router.put("/{type_id}", response_model=ProductTypeRead)
async def update_product_type(
    type_id: uuid.UUID,
    payload: ProductTypeUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.code == "BR":
        require_br_fiscal_admin(principal)
    pt = (await db.execute(select(ProductType).where(
        ProductType.id == type_id,
        ProductType.market_code == principal.code,
    ))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    old_name, old_group_id = pt.name, pt.group_id
    if principal.code == "BR" and payload.name != old_name:
        in_use = (await db.execute(select(exists().where(
            Product.market_code == "BR",
            Product.type == old_name,
            Product.is_active.is_(True),
        )))).scalar_one()
        if in_use:
            raise HTTPException(status_code=409, detail="Tipo em uso por produto BR; reclassifique os produtos antes de renomear.")
    if principal.code != "BR":
        await _require_group_in_market(db, payload.group_id, principal.code)
    old_ipi = await group_ipi(db, old_group_id) if principal.code == "BR" else None
    new_ipi = await group_ipi(db, payload.group_id) if principal.code == "BR" else None
    if principal.code == "BR" and payload.group_id is not None and new_ipi is None:
        raise HTTPException(status_code=422, detail="Grupo fiscal BR não encontrado.")
    pt.name = payload.name
    pt.group_id = payload.group_id
    if principal.code == "BR" and (old_name != pt.name or old_group_id != pt.group_id):
        record_product_type_fiscal_event(
            db, product_type_id=pt.id, actor_user_id=principal.user.id,
            market_code=principal.code, action="updated", source="api",
            old_name=old_name, new_name=pt.name,
            old_group_id=old_group_id, new_group_id=pt.group_id,
            old_ipi=old_ipi,
            new_ipi=new_ipi,
        )
    try:
        await db.commit()
        await db.refresh(pt)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tipo de móvel já existe.")
    return pt


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.code == "BR":
        require_br_fiscal_admin(principal)
    pt = (await db.execute(select(ProductType).where(
        ProductType.id == type_id,
        ProductType.market_code == principal.code,
    ))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    if principal.code == "BR":
        in_use = (await db.execute(select(exists().where(
            Product.market_code == "BR",
            Product.type == pt.name,
            Product.is_active.is_(True),
        )))).scalar_one()
        if in_use:
            raise HTTPException(status_code=409, detail="Tipo em uso por produto BR; reclassifique os produtos antes de excluir.")
        record_product_type_fiscal_event(
            db, product_type_id=pt.id, actor_user_id=principal.user.id,
            market_code=principal.code, action="deleted", source="api",
            old_name=pt.name, new_name=None,
            old_group_id=pt.group_id, new_group_id=None,
            old_ipi=await group_ipi(db, pt.group_id), new_ipi=None,
        )
    await db.delete(pt)
    await db.commit()
