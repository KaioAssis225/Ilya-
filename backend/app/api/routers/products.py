import uuid
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductUpdate, ProductRead
from app.core.config import settings

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


def _build_photo_url(request: Request, photo_path: Optional[str]) -> Optional[str]:
    if not photo_path:
        return None
    filename = os.path.basename(photo_path)
    return str(request.base_url) + f"static/uploads/{filename}"


def _to_read(product: Product, request: Request) -> ProductRead:
    data = ProductRead.model_validate(product)
    data.photo_url = _build_photo_url(request, product.photo_path)
    return data


@router.get("", response_model=List[ProductRead])
async def list_products(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(Product).offset(skip).limit(limit))
    return [_to_read(p, request) for p in result.scalars().all()]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    existing = await db.execute(
        select(Product).where(Product.product_code == payload.product_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código '{payload.product_code}' já existe.")
    product = Product(**payload.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return _to_read(product, request)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    request: Request,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return _to_read(product, request)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    request: Request,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return _to_read(product, request)


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
    request: Request,
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
    return _to_read(product, request)
