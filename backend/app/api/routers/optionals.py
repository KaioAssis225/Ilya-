import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_principal, get_db_session, require_platform_capability, require_roles
from app.core.markets import MarketPrincipal, PlatformPrincipal
from app.models.optional_color import OptionalColor
from app.models.optional_category import OptionalCategory
from app.models.user import User, UserRole
from app.schemas.optional import OptionalColorCreate, OptionalColorUpdate, OptionalColorRead
from app.core.config import settings
from app.core.uploads import build_photo_url, build_thumbnail_url, delete_upload, persist_upload, sanitize_image_upload

router = APIRouter(prefix="/api/v1/optionals", tags=["optionals"])

_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.produtos))
_ADMIN = Depends(require_roles(UserRole.admin, UserRole.produtos))
_ANY = Depends(
    require_roles(
        UserRole.admin,
        UserRole.vendedor,
        UserRole.representante,
        UserRole.cliente,
        UserRole.produtos,
    )
)


def _build_photo_url(photo_path: Optional[str]) -> Optional[str]:
    return build_photo_url(photo_path)


def _to_read(opt: OptionalColor) -> OptionalColorRead:
    data = OptionalColorRead.model_validate(opt)
    data.photo_url = _build_photo_url(opt.photo_path)
    data.thumbnail_url = build_thumbnail_url(opt.photo_path)
    return data


@router.get("", response_model=List[OptionalColorRead])
async def list_optionals(
    category: str | None = Query(default=None),
    categories: str | None = Query(default=None, max_length=3000),
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    stmt = select(OptionalColor).where(OptionalColor.market_code == principal.code)
    if category:
        stmt = stmt.where(OptionalColor.category == category)
    elif categories:
        category_values = [
            value.strip()
            for value in categories.split(",")
            if value.strip()
        ][:50]
        if category_values:
            stmt = stmt.where(OptionalColor.category.in_(category_values))
    result = await db.execute(
        stmt
        .order_by(
            OptionalColor.category,
            OptionalColor.color_name,
            OptionalColor.id,
        )
        .offset(skip)
        .limit(limit)
    )
    return [_to_read(o) for o in result.scalars().all()]


@router.post("", response_model=OptionalColorRead, status_code=status.HTTP_201_CREATED)
async def create_optional(
    payload: OptionalColorCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    category_exists = (await db.execute(select(OptionalCategory.id).where(
        OptionalCategory.market_code == principal.code,
        OptionalCategory.code == payload.category,
    ))).scalar_one_or_none()
    if category_exists is None:
        raise HTTPException(status_code=422, detail="Categoria de opcional não pertence ao mercado ativo.")
    opt = OptionalColor(market_code=principal.code, **payload.model_dump())
    db.add(opt)
    await db.commit()
    await db.refresh(opt)
    return _to_read(opt)


@router.get("/platform/EU", response_model=List[OptionalColorRead])
async def list_europe_optionals_before_activation(
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    rows = (await db.execute(select(OptionalColor).where(
        OptionalColor.market_code == "EU"
    ).order_by(
        OptionalColor.category,
        OptionalColor.color_name,
        OptionalColor.id,
    ).execution_options(skip_market_scope=True))).scalars().all()
    return [_to_read(optional) for optional in rows]


@router.post("/platform/EU", response_model=OptionalColorRead, status_code=status.HTTP_201_CREATED)
async def create_europe_optional_before_activation(
    payload: OptionalColorCreate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    category_exists = (await db.execute(select(OptionalCategory.id).where(
        OptionalCategory.market_code == "EU",
        OptionalCategory.code == payload.category,
    ).execution_options(skip_market_scope=True))).scalar_one_or_none()
    if category_exists is None:
        raise HTTPException(status_code=422, detail="Categoria de opcional não pertence ao mercado EU.")
    optional = OptionalColor(market_code="EU", **payload.model_dump())
    db.add(optional)
    await db.commit()
    await db.refresh(optional)
    return _to_read(optional)


@router.patch("/{optional_id}", response_model=OptionalColorRead)
async def update_optional(
    optional_id: uuid.UUID,
    payload: OptionalColorUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(OptionalColor).where(
        OptionalColor.id == optional_id,
        OptionalColor.market_code == principal.code,
    ))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    if payload.category is not None:
        category_exists = (await db.execute(select(OptionalCategory.id).where(
            OptionalCategory.market_code == principal.code,
            OptionalCategory.code == payload.category,
        ))).scalar_one_or_none()
        if category_exists is None:
            raise HTTPException(status_code=422, detail="Categoria de opcional não pertence ao mercado ativo.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opt, field, value)
    await db.commit()
    await db.refresh(opt)
    return _to_read(opt)


@router.delete("/{optional_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_optional(
    optional_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(OptionalColor).where(
        OptionalColor.id == optional_id,
        OptionalColor.market_code == principal.code,
    ))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    old_photo_path = opt.photo_path
    await db.delete(opt)
    await db.commit()
    # Opcional EU ainda não sincronizado aponta para a foto do opcional BR de
    # origem; `market` impede que a exclusão alcance o arquivo brasileiro.
    await delete_upload(old_photo_path, market=opt.market_code)


@router.post("/{optional_id}/upload-photo", response_model=OptionalColorRead)
async def upload_photo(
    optional_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(OptionalColor).where(
        OptionalColor.id == optional_id,
        OptionalColor.market_code == principal.code,
    ))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    content, ext = await sanitize_image_upload(
        file,
        max_bytes=settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        max_size_label=f"{settings.MAX_UPLOAD_SIZE_MB}MB",
        allowed_extensions=settings.get_allowed_extensions(),
        max_pixels=settings.MAX_IMAGE_PIXELS,
        max_dimension=settings.MAX_IMAGE_DIMENSION,
    )
    opt_dir = os.path.join(settings.UPLOAD_DIR, "optionals")
    old_photo_path = opt.photo_path
    save_path = await persist_upload(content, opt_dir, ext, market=opt.market_code)
    opt.photo_path = save_path
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await delete_upload(save_path)
        raise
    await delete_upload(old_photo_path, market=opt.market_code)
    await db.refresh(opt)
    return _to_read(opt)
