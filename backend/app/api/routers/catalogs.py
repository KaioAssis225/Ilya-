import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session, require_roles
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
):
    result = await db.execute(select(Catalog).order_by(Catalog.name))
    return result.scalars().all()


@router.post("", response_model=CatalogRead, status_code=status.HTTP_201_CREATED)
async def create_catalog(
    payload: CatalogCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    catalog = Catalog(name=payload.name.strip())
    db.add(catalog)
    try:
        await db.commit()
        await db.refresh(catalog)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Catálogo já existe.")
    return catalog


@router.put("/{catalog_id}", response_model=CatalogRead)
async def update_catalog(
    catalog_id: uuid.UUID,
    payload: CatalogUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    catalog = await db.get(Catalog, catalog_id)
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
):
    catalog = await db.get(Catalog, catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="Catálogo não encontrado.")
    # Excluir um catálogo em uso deixaria os produtos órfãos e sumindo do
    # filtro sem aviso. Bloqueia e informa quantos itens dependem dele.
    in_use = await db.scalar(
        select(func.count()).select_from(Product).where(Product.catalog_id == catalog_id)
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Catálogo em uso por {in_use} produto(s). Mova-os antes de excluir.",
        )
    await db.delete(catalog)
    await db.commit()
