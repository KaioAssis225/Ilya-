import uuid
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import load_only, noload

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.product import Product, ProductSetItem, ProductSetComponent
from app.models.product_type import ProductType
from app.models.optional_color import OptionalColor
from app.models.user import User, UserRole
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductRead,
    ProductSetItemRead, ProductSetComponentCreate, ProductSetComponentRead,
    ProductBatchRequest,
)
from app.core.config import settings
from app.core.search import literal_contains_pattern
from app.core.uploads import build_photo_url, build_thumbnail_url, delete_upload, persist_upload, sanitize_image_upload

def _is_conjunto_type(type_: Optional[str]) -> bool:
    """Bloco 74: identifica 'conjuntos' por substring case-insensitive no nome
    do tipo (ex.: 'Conjunto de Jantar', 'conjuntos'), em vez de exigir o valor
    exato 'Conjunto'."""
    return "conjunto" in (type_ or "").lower()


router = APIRouter(prefix="/api/v1/products", tags=["products"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.produtos))
_ADMIN = Depends(require_roles(UserRole.admin, UserRole.produtos))


def _build_photo_url(photo_path: Optional[str]) -> Optional[str]:
    return build_photo_url(photo_path)


def _to_read(product: Product) -> ProductRead:
    data = ProductRead.model_validate(product)
    data.photo_url = _build_photo_url(product.photo_path)
    data.thumbnail_url = build_thumbnail_url(product.photo_path)
    for opt_read, opt_orm in zip(data.optionals, product.optionals):
        opt_read.photo_url = _build_photo_url(opt_orm.photo_path)
        opt_read.thumbnail_url = build_thumbnail_url(opt_orm.photo_path)
    data.set_items = [
        ProductSetItemRead(
            product_code=si.product.product_code,
            qty=si.qty,
            description=si.product.description,
            photo_url=_build_photo_url(si.product.photo_path),
            thumbnail_url=build_thumbnail_url(si.product.photo_path),
        )
        for si in product.set_items
    ]
    data.components = []
    for comp in product.components:
        comp_read = ProductSetComponentRead.model_validate(comp)
        for opt_read, opt_orm in zip(comp_read.optionals, comp.optionals):
            opt_read.photo_url = _build_photo_url(opt_orm.photo_path)
            opt_read.thumbnail_url = build_thumbnail_url(opt_orm.photo_path)
        data.components.append(comp_read)
    return data


async def _resolve_set_items(
    db: AsyncSession, items: list, parent_code: str
) -> list[ProductSetItem]:
    codes = list(dict.fromkeys(item.product_code for item in items))
    products = (
        await db.execute(
            select(Product)
            .where(Product.product_code.in_(codes))
            .options(
                load_only(Product.id, Product.product_code, Product.is_set),
                noload(Product.optionals),
                noload(Product.set_items),
                noload(Product.components),
            )
        )
    ).scalars().all()
    product_map = {product.product_code: product for product in products}
    result = []
    for item in items:
        p = product_map.get(item.product_code)
        if not p:
            raise HTTPException(400, f"Produto '{item.product_code}' não encontrado.")
        if p.is_set:
            raise HTTPException(400, f"Produto '{item.product_code}' é um conjunto — conjuntos não podem conter outros conjuntos.")
        if p.product_code == parent_code:
            raise HTTPException(400, "Um conjunto não pode conter a si mesmo.")
        result.append(ProductSetItem(id=uuid.uuid4(), product_id=p.id, qty=item.qty))
    return result


async def _resolve_components(
    db: AsyncSession, items: list[ProductSetComponentCreate]
) -> list[ProductSetComponent]:
    optional_ids = {
        optional_id
        for item in items
        for optional_id in item.optional_ids
    }
    optionals = (
        await db.execute(
            select(OptionalColor).where(OptionalColor.id.in_(optional_ids))
        )
    ).scalars().all() if optional_ids else []
    optional_map = {optional.id: optional for optional in optionals}
    result = []
    for item in items:
        missing = [optional_id for optional_id in item.optional_ids if optional_id not in optional_map]
        if missing:
            raise HTTPException(status_code=400, detail="Um ou mais opcionais não foram encontrados.")
        comp = ProductSetComponent(
            id=uuid.uuid4(),
            description=item.description,
            is_circular=item.is_circular,
            altura=item.altura,
            largura=item.largura,
            profundidade=item.profundidade,
            qty=item.qty,
        )
        comp.optionals = [optional_map[optional_id] for optional_id in item.optional_ids]
        result.append(comp)
    return result


async def _resolve_optionals(db: AsyncSession, ids: list[uuid.UUID]) -> list[OptionalColor]:
    if not ids:
        return []
    result = await db.execute(select(OptionalColor).where(OptionalColor.id.in_(ids)))
    return list(result.scalars().all())


@router.get("", response_model=List[ProductRead])
async def list_products(
    response: Response,
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=100, ge=1, le=1000),
    q: Optional[str] = Query(default=None, max_length=200),
    product_type: Optional[str] = Query(
        default=None,
        alias="type",
        max_length=50,
    ),
    group_id: uuid.UUID | None = Query(default=None),
    include_total: bool = Query(default=True),
    sort_by: Literal[
        "product_code",
        "description",
        "type",
        "price_lojista",
        "price_corporativo",
    ] = Query(default="product_code"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    filters = []
    search = q.strip() if q else ""
    if search:
        search_pattern = literal_contains_pattern(search)
        filters.append(
            or_(
                Product.product_code.ilike(search_pattern, escape="\\"),
                Product.description.ilike(search_pattern, escape="\\"),
            )
        )
    if product_type:
        filters.append(Product.type == product_type)
    if group_id:
        filters.append(
            Product.type.in_(
                select(ProductType.name).where(
                    ProductType.group_id == group_id
                )
            )
        )

    sort_column = {
        "product_code": Product.product_code,
        # Evita um índice B-tree inseguro sobre textos de até 20 mil caracteres.
        # Os primeiros 512 caracteres cobrem a ordenação visual do catálogo e
        # permitem um índice pequeno e previsível.
        "description": func.left(
            Product.description,
            literal_column("512"),
        ),
        "type": Product.type,
        "price_lojista": Product.price_lojista,
        "price_corporativo": Product.price_corporativo,
    }[sort_by]
    order_expression = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    id_order = Product.id.desc() if sort_dir == "desc" else Product.id.asc()

    total: int | None = None
    if include_total:
        total = (
            await db.execute(
                select(func.count()).select_from(Product).where(*filters)
            )
        ).scalar_one()
    result = await db.execute(
        select(Product)
        .where(*filters)
        .order_by(order_expression, id_order)
        .offset(skip)
        .limit(limit if include_total else limit + 1)
    )
    loaded_products = list(result.scalars().all())
    products = loaded_products[:limit]
    has_more = (
        skip + len(products) < total
        if total is not None
        else len(loaded_products) > limit
    )
    if total is not None:
        response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(products))
    return [_to_read(product) for product in products]


@router.post("/batch", response_model=List[ProductRead])
async def get_products_batch(
    payload: ProductBatchRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    codes = list(dict.fromkeys(payload.product_codes))
    products = (
        await db.execute(select(Product).where(Product.product_code.in_(codes)))
    ).scalars().all()
    product_map = {product.product_code: product for product in products}
    return [_to_read(product_map[code]) for code in codes if code in product_map]


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
    product_data = payload.model_dump(exclude={"optional_ids", "set_items", "components"})
    product = Product(**product_data)
    product.optionals = await _resolve_optionals(db, payload.optional_ids)
    if payload.is_set:
        product.set_items = await _resolve_set_items(db, payload.set_items, payload.product_code)
    if _is_conjunto_type(payload.type) and payload.components:
        product.components = await _resolve_components(db, payload.components)
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
    data = payload.model_dump(exclude_unset=True, exclude={"optional_ids", "set_items", "components"})
    optional_ids = payload.optional_ids
    set_items_in = payload.set_items
    components_in = payload.components
    for field, value in data.items():
        setattr(product, field, value)
    if optional_ids is not None:
        product.optionals = await _resolve_optionals(db, optional_ids)
    if set_items_in is not None:
        if product.is_set:
            product.set_items = await _resolve_set_items(db, set_items_in, product.product_code)
        else:
            product.set_items = []
    if components_in is not None:
        if _is_conjunto_type(product.type):
            product.components = await _resolve_components(db, components_in)
        else:
            product.components = []
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
    old_photo_path = product.photo_path
    await db.delete(product)
    await db.commit()
    await delete_upload(old_photo_path)


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
    content, ext = await sanitize_image_upload(
        file,
        max_bytes=settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        max_size_label=f"{settings.MAX_UPLOAD_SIZE_MB}MB",
        allowed_extensions=settings.get_allowed_extensions(),
        max_pixels=settings.MAX_IMAGE_PIXELS,
        max_dimension=settings.MAX_IMAGE_DIMENSION,
    )
    old_photo_path = product.photo_path
    save_path = await persist_upload(content, settings.UPLOAD_DIR, ext)
    product.photo_path = save_path
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await delete_upload(save_path)
        raise
    await delete_upload(old_photo_path)
    await db.refresh(product)
    return _to_read(product)
