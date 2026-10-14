import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_principal, get_db_session, require_platform_capability, require_roles
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.optional_category import OptionalCategoryCreate, OptionalCategoryUpdate, OptionalCategoryRead

router = APIRouter(prefix="/api/v1/optional-categories", tags=["optional-categories"])

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


@router.get("", response_model=List[OptionalCategoryRead])
async def list_optional_categories(
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(OptionalCategory).where(
        OptionalCategory.market_code == principal.code
    ).order_by(OptionalCategory.name))
    return result.scalars().all()


@router.post("", response_model=OptionalCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_optional_category(
    payload: OptionalCategoryCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    cat = OptionalCategory(market_code=principal.code, **payload.model_dump())
    db.add(cat)
    try:
        await db.commit()
        await db.refresh(cat)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Código de categoria já existe.")
    return cat


@router.get("/platform/EU", response_model=List[OptionalCategoryRead])
async def list_europe_optional_categories_before_activation(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    return (await db.execute(select(OptionalCategory).where(
        OptionalCategory.market_code == "EU"
    ).order_by(OptionalCategory.name).execution_options(skip_market_scope=True))).scalars().all()


@router.post("/platform/EU", response_model=OptionalCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_europe_optional_category_before_activation(
    payload: OptionalCategoryCreate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    category = OptionalCategory(market_code="EU", **payload.model_dump())
    db.add(category)
    try:
        await db.commit()
        await db.refresh(category)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Código de categoria já existe no mercado EU.")
    return category


@router.put("/{category_id}", response_model=OptionalCategoryRead)
async def update_optional_category(
    category_id: uuid.UUID,
    payload: OptionalCategoryUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    cat = (await db.execute(select(OptionalCategory).where(
        OptionalCategory.id == category_id,
        OptionalCategory.market_code == principal.code,
    ))).scalar_one_or_none()
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
                .where(
                    OptionalColor.category == old_code,
                    OptionalColor.market_code == principal.code,
                )
                .values(category=payload.code)
            )
            product_rows = (await db.execute(select(
                Product.id,
                Product.all_optionals_categories,
            ).where(
                Product.market_code == principal.code,
                Product.all_optionals_categories.is_not(None),
            ))).all()
            for product_id, raw_categories in product_rows:
                codes = [code.strip() for code in raw_categories.split(",") if code.strip()]
                if old_code not in codes:
                    continue
                await db.execute(
                    update(Product)
                    .where(
                        Product.id == product_id,
                        Product.market_code == principal.code,
                    )
                    .values(all_optionals_categories=",".join(
                        payload.code if code == old_code else code for code in codes
                    ))
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
    principal: MarketPrincipal = Depends(get_current_principal),
):
    cat = (await db.execute(select(OptionalCategory).where(
        OptionalCategory.id == category_id,
        OptionalCategory.market_code == principal.code,
    ))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    in_use = await db.scalar(
        select(func.count()).select_from(OptionalColor).where(
            OptionalColor.category == cat.code,
            OptionalColor.market_code == principal.code,
        )
    )
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Categoria em uso por {in_use} opcional(is). Remova as opções antes de excluir a categoria.",
        )
    await db.delete(cat)
    await db.commit()
