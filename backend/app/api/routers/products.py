import uuid
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.product import Product
from app.models.optional_color import OptionalColor
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductUpdate, ProductRead
from app.core.config import settings

_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",
}


def _detect_mime(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


router = APIRouter(prefix="/api/v1/products", tags=["products"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


def _build_photo_url(photo_path: Optional[str]) -> Optional[str]:
    if not photo_path:
        return None
    # Filesystem path (app/static/uploads/x.jpg) → web path (/static/uploads/x.jpg)
    if photo_path.startswith("app/"):
        return "/" + photo_path[4:]
    return "/static/uploads/" + os.path.basename(photo_path)


def _to_read(product: Product) -> ProductRead:
    data = ProductRead.model_validate(product)
    data.photo_url = _build_photo_url(product.photo_path)
    for opt_read, opt_orm in zip(data.optionals, product.optionals):
        opt_read.photo_url = _build_photo_url(opt_orm.photo_path)
    return data


async def _resolve_optionals(db: AsyncSession, ids: list[uuid.UUID]) -> list[OptionalColor]:
    if not ids:
        return []
    result = await db.execute(select(OptionalColor).where(OptionalColor.id.in_(ids)))
    return list(result.scalars().all())


@router.get("", response_model=List[ProductRead])
async def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(Product).offset(skip).limit(limit))
    return [_to_read(p) for p in result.scalars().all()]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    existing = await db.execute(
        select(Product).where(Product.product_code == payload.product_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código '{payload.product_code}' já existe.")
    product_data = payload.model_dump(exclude={"optional_ids"})
    product = Product(**product_data)
    product.optionals = await _resolve_optionals(db, payload.optional_ids)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return _to_read(product)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return _to_read(product)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    data = payload.model_dump(exclude_unset=True)
    optional_ids = data.pop("optional_ids", None)
    for field, value in data.items():
        setattr(product, field, value)
    if optional_ids is not None:
        product.optionals = await _resolve_optionals(db, optional_ids)
    await db.commit()
    await db.refresh(product)
    return _to_read(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if product.photo_path and os.path.exists(product.photo_path):
        os.remove(product.photo_path)
    await db.delete(product)
    await db.commit()


@router.post("/{product_id}/upload-photo", response_model=ProductRead)
async def upload_photo(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    ext = os.path.splitext(file.filename or "")[-1].lower().lstrip(".")
    if ext not in settings.get_allowed_extensions():
        raise HTTPException(status_code=422, detail=f"Extensão '{ext}' não permitida.")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")
    detected = _detect_mime(content)
    if detected is None or detected not in settings.get_allowed_extensions():
        raise HTTPException(status_code=422, detail="Conteúdo do arquivo não é uma imagem válida.")
    if product.photo_path and os.path.exists(product.photo_path):
        os.remove(product.photo_path)
    filename = f"{uuid.uuid4()}.{ext}"
    save_path = os.path.join(settings.UPLOAD_DIR, filename)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(content)
    product.photo_path = save_path
    await db.commit()
    await db.refresh(product)
    return _to_read(product)
