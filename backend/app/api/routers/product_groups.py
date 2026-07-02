import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session, require_roles
from app.models.product_group import ProductGroup
from app.models.user import UserRole
from app.schemas.product_group import ProductGroupCreate, ProductGroupUpdate, ProductGroupRead

router = APIRouter(prefix="/api/v1/product-groups", tags=["product-groups"])

_ANY = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.representante))
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


@router.get("", response_model=List[ProductGroupRead])
async def list_product_groups(
    db: AsyncSession = Depends(get_db_session),
    _=_ANY,
):
    result = await db.execute(select(ProductGroup).order_by(ProductGroup.name))
    return result.scalars().all()


@router.post("", response_model=ProductGroupRead, status_code=status.HTTP_201_CREATED)
async def create_product_group(
    payload: ProductGroupCreate,
    db: AsyncSession = Depends(get_db_session),
    _=_ADMIN_VENDEDOR,
):
    pg = ProductGroup(id=uuid.uuid4(), **payload.model_dump())
    db.add(pg)
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
    _=_ADMIN_VENDEDOR,
):
    pg = await db.get(ProductGroup, group_id)
    if not pg:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
    if payload.name is not None:
        pg.name = payload.name
    if payload.ipi is not None:
        pg.ipi = payload.ipi
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
    _=_ADMIN,
):
    pg = await db.get(ProductGroup, group_id)
    if not pg:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
    await db.delete(pg)
    await db.commit()
