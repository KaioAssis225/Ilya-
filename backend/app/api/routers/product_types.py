import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_platform_capability, require_roles
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.models.product_type import ProductType
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
    data = payload.model_dump()
    if principal.code == "EU" and data.get("group_id") is not None:
        raise HTTPException(status_code=422, detail="Tipo EU não pode herdar grupo fiscal brasileiro.")
    pt = ProductType(market_code=principal.code, **data)
    db.add(pt)
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
    if payload.group_id is not None:
        raise HTTPException(status_code=422, detail="Tipo EU não pode herdar grupo fiscal brasileiro.")
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
    pt = (await db.execute(select(ProductType).where(
        ProductType.id == type_id,
        ProductType.market_code == principal.code,
    ))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    pt.name = payload.name
    if principal.code == "EU" and payload.group_id is not None:
        raise HTTPException(status_code=422, detail="Tipo EU não pode herdar grupo fiscal brasileiro.")
    pt.group_id = payload.group_id
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
    pt = (await db.execute(select(ProductType).where(
        ProductType.id == type_id,
        ProductType.market_code == principal.code,
    ))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    await db.delete(pt)
    await db.commit()
