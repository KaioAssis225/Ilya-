import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session, require_roles
from app.models.product_type import ProductType
from app.models.user import User, UserRole
from app.schemas.product_type import ProductTypeCreate, ProductTypeUpdate, ProductTypeRead

router = APIRouter(prefix="/api/v1/product-types", tags=["product-types"])

_ANY = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.representante))
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


@router.get("", response_model=List[ProductTypeRead])
async def list_product_types(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(ProductType).order_by(ProductType.name))
    return result.scalars().all()


@router.post("", response_model=ProductTypeRead, status_code=status.HTTP_201_CREATED)
async def create_product_type(
    payload: ProductTypeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    pt = ProductType(**payload.model_dump())
    db.add(pt)
    try:
        await db.commit()
        await db.refresh(pt)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tipo de móvel já existe.")
    return pt


@router.put("/{type_id}", response_model=ProductTypeRead)
async def update_product_type(
    type_id: uuid.UUID,
    payload: ProductTypeUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    pt = await db.get(ProductType, type_id)
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    pt.name = payload.name
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
):
    pt = await db.get(ProductType, type_id)
    if not pt:
        raise HTTPException(status_code=404, detail="Tipo não encontrado.")
    await db.delete(pt)
    await db.commit()
