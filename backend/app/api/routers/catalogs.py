import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_platform_capability, require_roles
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.models.catalog import Catalog
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.catalog import CatalogCreate, CatalogUpdate, CatalogRead

router = APIRouter(prefix="/api/v1/catalogs", tags=["catalogs"])

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


@router.get("", response_model=List[CatalogRead])
async def list_catalogs(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(Catalog).where(
        Catalog.market_code == principal.code
    ).order_by(Catalog.name))
    return result.scalars().all()


@router.post("", response_model=CatalogRead, status_code=status.HTTP_201_CREATED)
async def create_catalog(
    payload: CatalogCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    catalog = Catalog(market_code=principal.code, name=payload.name.strip())
    db.add(catalog)
    try:
        await db.commit()
        await db.refresh(catalog)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Catálogo já existe.")
    return catalog


@router.get("/platform/EU", response_model=List[CatalogRead])
async def list_europe_catalogs_before_activation(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    return (await db.execute(select(Catalog).where(
        Catalog.market_code == "EU"
    ).order_by(Catalog.name).execution_options(skip_market_scope=True))).scalars().all()


@router.post("/platform/EU", response_model=CatalogRead, status_code=status.HTTP_201_CREATED)
async def create_europe_catalog_before_activation(
    payload: CatalogCreate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    catalog = Catalog(market_code="EU", name=payload.name.strip())
    db.add(catalog)
    try:
        await db.commit()
        await db.refresh(catalog)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Catálogo já existe no mercado EU.")
    return catalog


@router.put("/{catalog_id}", response_model=CatalogRead)
async def update_catalog(
    catalog_id: uuid.UUID,
    payload: CatalogUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    catalog = (await db.execute(select(Catalog).where(
        Catalog.id == catalog_id,
        Catalog.market_code == principal.code,
    ))).scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
    catalog.name = payload.name.strip()
    try:
        await db.commit()
        await db.refresh(catalog)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Catálogo já existe.")
    return catalog


@router.delete("/{catalog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog(
    catalog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    catalog = (await db.execute(select(Catalog).where(
        Catalog.id == catalog_id,
        Catalog.market_code == principal.code,
    ))).scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
    # Excluir um catálogo em uso deixaria os produtos órfãos e sumindo do
    # filtro sem aviso. Bloqueia e informa quantos itens dependem dele.
    in_use = await db.scalar(
        select(func.count()).select_from(Product).where(
            Product.catalog_id == catalog_id,
            Product.market_code == principal.code,
        )
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Catálogo em uso por {in_use} produto(s). Mova-os antes de excluir.",
        )
    await db.delete(catalog)
    await db.commit()
