import uuid
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_showroom_manager
from app.core.markets import MarketPrincipal
from app.core.search import literal_contains_pattern
from app.core.uploads import build_thumbnail_url
from app.models.market import PriceList, ProductMarket, ProductPrice
from app.models.product import Product
from app.models.showroom import ShowroomBox, ShowroomBoxItem
from app.schemas.showroom import (
    ShowroomBoxCreate,
    ShowroomBoxRead,
    ShowroomBoxUpdate,
    ShowroomItemAdd,
    ShowroomItemRead,
    ShowroomItemUpdate,
    ShowroomProductRead,
)


router = APIRouter(prefix="/api/v1/showroom-boxes", tags=["showroom-boxes"])
_MANAGER = Depends(require_showroom_manager)


async def _get_box(db: AsyncSession, box_id: uuid.UUID) -> ShowroomBox:
    box = (await db.execute(
        select(ShowroomBox).where(
            ShowroomBox.id == box_id,
            ShowroomBox.market_code == "EU",
        )
    )).scalar_one_or_none()
    if box is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Box não encontrada.")
    return box


async def _ensure_active_price_list(db: AsyncSession, code: str) -> None:
    found = (await db.execute(select(PriceList.id).where(
        PriceList.market_code == "EU",
        PriceList.code == code,
        PriceList.is_active.is_(True),
    ))).scalar_one_or_none()
    if found is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tabela de preço EU indisponível.")


async def _read_box(db: AsyncSession, box: ShowroomBox) -> ShowroomBoxRead:
    rows = (await db.execute(
        select(ShowroomBoxItem, Product, ProductPrice.amount)
        .join(Product, Product.id == ShowroomBoxItem.product_id)
        .join(
            PriceList,
            (PriceList.market_code == "EU")
            & (PriceList.code == box.price_list_code),
        )
        .outerjoin(
            ProductPrice,
            (ProductPrice.product_id == Product.id)
            & (ProductPrice.price_list_id == PriceList.id),
        )
        .where(ShowroomBoxItem.box_id == box.id)
        .order_by(Product.product_code, ShowroomBoxItem.id)
        .execution_options(skip_market_scope=True)
    )).all()
    items: list[ShowroomItemRead] = []
    total_value = Decimal("0.00")
    total_quantity = 0
    for item, product, amount in rows:
        unit = Decimal(amount or 0)
        line_total = unit * item.quantity
        total_quantity += item.quantity
        total_value += line_total
        items.append(ShowroomItemRead(
            item_id=item.id,
            id=product.id,
            product_code=product.product_code,
            description=product.description,
            thumbnail_url=build_thumbnail_url(product.photo_path),
            unit_price=unit,
            quantity=item.quantity,
            line_total=line_total,
        ))
    return ShowroomBoxRead(
        id=box.id,
        name=box.name,
        price_list_code=box.price_list_code,
        items=items,
        item_count=len(items),
        total_quantity=total_quantity,
        total_value=total_value,
        created_at=box.created_at,
        updated_at=box.updated_at,
    )


@router.get("", response_model=List[ShowroomBoxRead])
async def list_boxes(
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    boxes = list((await db.execute(
        select(ShowroomBox)
        .where(ShowroomBox.market_code == principal.code)
        .order_by(ShowroomBox.updated_at.desc(), ShowroomBox.name)
    )).scalars().all())
    return [await _read_box(db, box) for box in boxes]


@router.post("", response_model=ShowroomBoxRead, status_code=status.HTTP_201_CREATED)
async def create_box(
    payload: ShowroomBoxCreate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _ensure_active_price_list(db, payload.price_list_code)
    box = ShowroomBox(
        market_code=principal.code,
        name=payload.name,
        price_list_code=payload.price_list_code,
        created_by_user_id=principal.user.id,
    )
    db.add(box)
    await db.commit()
    await db.refresh(box)
    return await _read_box(db, box)


@router.get("/products", response_model=List[ShowroomProductRead])
async def search_products(
    price_list_code: str = Query(..., pattern="^(lojista|arquiteto|corporativo|pvp)$"),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _ensure_active_price_list(db, price_list_code)
    filters = [
        Product.market_code == principal.code,
        Product.is_active.is_(True),
        Product.is_prototype.is_(False),
        ProductMarket.market_code == principal.code,
        ProductMarket.is_available.is_(True),
    ]
    search = q.strip()
    if search:
        pattern = literal_contains_pattern(search)
        filters.append(or_(
            Product.product_code.ilike(pattern, escape="\\"),
            Product.description.ilike(pattern, escape="\\"),
        ))
    rows = (await db.execute(
        select(Product, ProductPrice.amount)
        .join(ProductMarket, ProductMarket.product_id == Product.id)
        .join(
            PriceList,
            (PriceList.market_code == principal.code)
            & (PriceList.code == price_list_code)
            & (PriceList.is_active.is_(True)),
        )
        .join(
            ProductPrice,
            (ProductPrice.product_id == Product.id)
            & (ProductPrice.price_list_id == PriceList.id),
        )
        .where(*filters)
        .order_by(Product.product_code)
        .limit(limit)
        .execution_options(skip_market_scope=True)
    )).all()
    return [ShowroomProductRead(
        id=product.id,
        product_code=product.product_code,
        description=product.description,
        thumbnail_url=build_thumbnail_url(product.photo_path),
        unit_price=amount,
    ) for product, amount in rows]


@router.patch("/{box_id}", response_model=ShowroomBoxRead)
async def update_box(
    box_id: uuid.UUID,
    payload: ShowroomBoxUpdate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    data = payload.model_dump(exclude_unset=True)
    next_price_list = data.get("price_list_code")
    if next_price_list and next_price_list != box.price_list_code:
        await _ensure_active_price_list(db, next_price_list)
        missing = (await db.execute(
            select(func.count())
            .select_from(ShowroomBoxItem)
            .join(Product, Product.id == ShowroomBoxItem.product_id)
            .join(
                PriceList,
                (PriceList.market_code == "EU") & (PriceList.code == next_price_list),
            )
            .outerjoin(
                ProductPrice,
                (ProductPrice.product_id == Product.id)
                & (ProductPrice.price_list_id == PriceList.id),
            )
            .where(ShowroomBoxItem.box_id == box.id, ProductPrice.product_id.is_(None))
            .execution_options(skip_market_scope=True)
        )).scalar_one()
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{missing} produto(s) não possuem preço nessa tabela.",
            )
    for field, value in data.items():
        setattr(box, field, value)
    await db.commit()
    await db.refresh(box)
    return await _read_box(db, box)


@router.delete("/{box_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_box(
    box_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    await db.delete(box)
    await db.commit()


@router.post("/{box_id}/items", response_model=ShowroomBoxRead)
async def add_item(
    box_id: uuid.UUID,
    payload: ShowroomItemAdd,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    priced_product = (await db.execute(
        select(Product.id)
        .join(ProductMarket, ProductMarket.product_id == Product.id)
        .join(
            PriceList,
            (PriceList.market_code == principal.code)
            & (PriceList.code == box.price_list_code)
            & (PriceList.is_active.is_(True)),
        )
        .join(
            ProductPrice,
            (ProductPrice.product_id == Product.id)
            & (ProductPrice.price_list_id == PriceList.id),
        )
        .where(
            Product.id == payload.product_id,
            Product.market_code == principal.code,
            Product.is_active.is_(True),
            Product.is_prototype.is_(False),
            ProductMarket.market_code == principal.code,
            ProductMarket.is_available.is_(True),
        )
        .execution_options(skip_market_scope=True)
    )).scalar_one_or_none()
    if priced_product is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Produto EU indisponível ou sem preço na tabela selecionada.",
        )
    upserted = (await db.execute(
        pg_insert(ShowroomBoxItem)
        .values(
            box_id=box.id,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
        .on_conflict_do_update(
            constraint="uq_showroom_box_items_product",
            set_={
                "quantity": ShowroomBoxItem.quantity + payload.quantity,
                "updated_at": func.now(),
            },
            where=ShowroomBoxItem.quantity + payload.quantity <= 1_000_000,
        )
        .returning(ShowroomBoxItem.id)
    )).scalar_one_or_none()
    if upserted is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A quantidade máxima por produto é 1.000.000.",
        )
    await db.commit()
    await db.refresh(box)
    return await _read_box(db, box)


@router.patch("/{box_id}/items/{item_id}", response_model=ShowroomBoxRead)
async def update_item(
    box_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ShowroomItemUpdate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    item = (await db.execute(select(ShowroomBoxItem).where(
        ShowroomBoxItem.id == item_id,
        ShowroomBoxItem.box_id == box.id,
    ))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produto não encontrado nesta box.")
    item.quantity = payload.quantity
    await db.commit()
    await db.refresh(box)
    return await _read_box(db, box)


@router.delete("/{box_id}/items/{item_id}", response_model=ShowroomBoxRead)
async def remove_item(
    box_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    removed = await db.execute(delete(ShowroomBoxItem).where(
        ShowroomBoxItem.id == item_id,
        ShowroomBoxItem.box_id == box.id,
    ))
    if not removed.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produto não encontrado nesta box.")
    await db.commit()
    await db.refresh(box)
    return await _read_box(db, box)
