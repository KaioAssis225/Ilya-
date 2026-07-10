import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session, require_roles
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.user import User, UserRole
from app.schemas.optional_category import OptionalCategoryCreate, OptionalCategoryUpdate, OptionalCategoryRead

router = APIRouter(prefix="/api/v1/optional-categories", tags=["optional-categories"])

_ANY = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.representante, UserRole.cliente))
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


@router.get("", response_model=List[OptionalCategoryRead])
async def list_optional_categories(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(OptionalCategory).order_by(OptionalCategory.name))
    return result.scalars().all()


@router.post("", response_model=OptionalCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_optional_category(
    payload: OptionalCategoryCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    cat = OptionalCategory(**payload.model_dump())
    db.add(cat)
    try:
        await db.commit()
        await db.refresh(cat)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Código de categoria já existe.")
    return cat


@router.put("/{category_id}", response_model=OptionalCategoryRead)
async def update_optional_category(
    category_id: uuid.UUID,
    payload: OptionalCategoryUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    cat = await db.get(OptionalCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    old_code = cat.code
    cat.name = payload.name
    cat.code = payload.code
    try:
        if old_code != payload.code:
            # Mantém os opcionais já cadastrados vinculados ao grupo renomeado,
            # evitando que fiquem "órfãos" com o código antigo (V-Bloco65-cats).
            await db.execute(
                update(OptionalColor)
                .where(OptionalColor.category == old_code)
                .values(category=payload.code)
            )
        await db.commit()
        await db.refresh(cat)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Código de categoria já existe.")
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_optional_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    cat = await db.get(OptionalCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    await db.delete(cat)
    await db.commit()
