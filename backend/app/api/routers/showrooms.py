import uuid
import hashlib
import json
from decimal import Decimal
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db_session, require_showroom_manager
from app.core.markets import MarketPrincipal
from app.core.search import literal_contains_pattern
from app.core.uploads import build_thumbnail_url
from app.models.market import PriceList, ProductMarket, ProductPrice
from app.models.optional_application import ProductOptionalApplication
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor, product_optionals
from app.models.product import Product, ProductSetComponent
from app.models.showroom import ShowroomBox, ShowroomBoxItem
from app.schemas.showroom import (
    ShowroomBoxCreate,
    ShowroomBoxRead,
    ShowroomBoxUpdate,
    ShowroomItemAdd,
    ShowroomItemRead,
    ShowroomItemUpdate,
    ShowroomOptionalChoiceInput,
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


def _localized_description(
    product: Product, product_market: ProductMarket, language: Literal["pt-PT", "en-GB"],
) -> str:
    localized = (
        product_market.description_en
        if language == "en-GB"
        else product_market.description_pt_pt
    )
    return localized or product.description


async def _read_box(
    db: AsyncSession,
    box: ShowroomBox,
    language: Literal["pt-PT", "en-GB"] = "pt-PT",
) -> ShowroomBoxRead:
    rows = (await db.execute(
        select(ShowroomBoxItem, Product, ProductMarket, ProductPrice.amount)
        .join(Product, Product.id == ShowroomBoxItem.product_id)
        .join(
            ProductMarket,
            (ProductMarket.product_id == Product.id)
            & (ProductMarket.market_code == "EU"),
        )
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
    optional_ids = {
        uuid.UUID(choice["optional_id"])
        for item, *_ in rows
        for choice in item.optional_configuration
        if choice.get("optional_id")
    }
    current_optionals = {
        row.id: row for row in (await db.execute(
            select(OptionalColor).where(OptionalColor.id.in_(optional_ids))
        )).scalars()
    } if optional_ids else {}
    for item, product, product_market, amount in rows:
        unit = Decimal(amount or 0)
        line_total = unit * item.quantity
        total_quantity += item.quantity
        total_value += line_total
        items.append(ShowroomItemRead(
            item_id=item.id,
            id=product.id,
            product_code=product.product_code,
            description=_localized_description(product, product_market, language),
            thumbnail_url=build_thumbnail_url(product.photo_path),
            unit_price=unit,
            quantity=item.quantity,
            line_total=line_total,
            optional_choices=[{
                **choice,
                "thumbnail_url": build_thumbnail_url(
                    current_optionals.get(uuid.UUID(choice["optional_id"])).photo_path
                ) if current_optionals.get(uuid.UUID(choice["optional_id"])) else None,
            } for choice in item.optional_configuration],
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
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    boxes = list((await db.execute(
        select(ShowroomBox)
        .where(ShowroomBox.market_code == principal.code)
        .order_by(ShowroomBox.updated_at.desc(), ShowroomBox.name)
    )).scalars().all())
    return [await _read_box(db, box, language) for box in boxes]


@router.post("", response_model=ShowroomBoxRead, status_code=status.HTTP_201_CREATED)
async def create_box(
    payload: ShowroomBoxCreate,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
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
    return await _read_box(db, box, language)


@router.get("/products", response_model=List[ShowroomProductRead])
async def search_products(
    price_list_code: str = Query(..., pattern="^(lojista|arquiteto|corporativo|pvp)$"),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
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
        localized_description = (
            ProductMarket.description_en
            if language == "en-GB"
            else ProductMarket.description_pt_pt
        )
        filters.append(or_(
            Product.product_code.ilike(pattern, escape="\\"),
            Product.description.ilike(pattern, escape="\\"),
            localized_description.ilike(pattern, escape="\\"),
        ))
    rows = (await db.execute(
        select(Product, ProductMarket, ProductPrice.amount)
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
        description=_localized_description(product, product_market, language),
        thumbnail_url=build_thumbnail_url(product.photo_path),
        unit_price=amount,
    ) for product, product_market, amount in rows]


@router.patch("/{box_id}", response_model=ShowroomBoxRead)
async def update_box(
    box_id: uuid.UUID,
    payload: ShowroomBoxUpdate,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
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
    return await _read_box(db, box, language)


@router.delete("/{box_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_box(
    box_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    await db.delete(box)
    await db.commit()


async def _optional_configuration(
    db: AsyncSession,
    product: Product,
    choices: list[ShowroomOptionalChoiceInput],
) -> tuple[list[dict], str]:
    applications = list((await db.execute(
        select(ProductOptionalApplication)
        .where(ProductOptionalApplication.product_id == product.id)
        .options(
            selectinload(ProductOptionalApplication.category),
            selectinload(ProductOptionalApplication.allowed_optionals),
        )
    )).scalars())
    applications_by_id = {row.id: row for row in applications}
    application_categories = {row.category.code for row in applications}

    repeated_slots = len({
        ("application", row.application_id)
        if row.application_id is not None
        else ("category", row.category_code)
        for row in choices
    }) != len(choices)
    if repeated_slots:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opcional repetido na mesma aplicação ou categoria.")

    optional_ids = {row.optional_id for row in choices}
    optionals = list((await db.execute(select(OptionalColor).where(
        OptionalColor.id.in_(optional_ids),
        OptionalColor.market_code == "EU",
    ))).scalars()) if optional_ids else []
    optionals_by_id = {row.id: row for row in optionals}
    if len(optionals_by_id) != len(optional_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opcional não existe no mercado EU.")

    component_ids = {row.component_id for row in applications if row.component_id is not None}
    components = list((await db.execute(select(ProductSetComponent).where(
        ProductSetComponent.id.in_(component_ids),
        ProductSetComponent.set_id == product.id,
    ))).scalars()) if component_ids else []
    components_by_id = {row.id: row for row in components}

    direct_rows = (await db.execute(
        select(product_optionals.c.optional_id, OptionalColor.category)
        .join(OptionalColor, OptionalColor.id == product_optionals.c.optional_id)
        .where(product_optionals.c.product_id == product.id)
    )).all()
    direct_ids_by_category: dict[str, set[uuid.UUID]] = {}
    for optional_id, category in direct_rows:
        direct_ids_by_category.setdefault(category, set()).add(optional_id)
    free_categories = {
        value.strip() for value in (product.all_optionals_categories or "").split(",")
        if value.strip()
    }
    legacy_categories = (set(direct_ids_by_category) | free_categories) - application_categories

    category_codes = {
        row.category_code for row in choices if row.category_code is not None
    }
    categories = list((await db.execute(select(OptionalCategory).where(
        OptionalCategory.market_code == "EU",
        OptionalCategory.code.in_(category_codes),
    ))).scalars()) if category_codes else []
    categories_by_code = {row.code: row for row in categories}

    snapshots: list[dict] = []
    used_application_optionals: dict[tuple[str, uuid.UUID], ProductOptionalApplication] = {}
    selected_application_ids: set[uuid.UUID] = set()
    for choice in choices:
        optional = optionals_by_id[choice.optional_id]
        if choice.application_id is not None:
            application = applications_by_id.get(choice.application_id)
            if application is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aplicação de opcional inválida para este produto.")
            if optional.category != application.category.code or (
                not application.allow_all
                and optional.id not in {row.id for row in application.allowed_optionals}
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Opção não autorizada em '{application.name}'.",
                )
            repeat_key = (application.category.code, optional.id)
            previous = used_application_optionals.get(repeat_key)
            if previous and (not previous.allow_repeat or not application.allow_repeat):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Opção repetida na categoria '{application.category.name}'.",
                )
            used_application_optionals[repeat_key] = application
            selected_application_ids.add(application.id)
            component = components_by_id.get(application.component_id)
            snapshots.append({
                "application_id": str(application.id),
                "application_name": application.name,
                "application_name_en": application.name_en,
                "component_name": component.description if component else None,
                "category_code": application.category.code,
                "category_name": application.category.name,
                "optional_id": str(optional.id),
                "optional_name": optional.color_name,
                "display_order": application.display_order,
            })
            continue

        category_code = choice.category_code or ""
        category = categories_by_code.get(category_code)
        if category is None or category_code not in legacy_categories:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Categoria de opcional inválida para este produto.")
        allowed_ids = direct_ids_by_category.get(category_code, set())
        if optional.category != category_code or (
            category_code not in free_categories and optional.id not in allowed_ids
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opção não autorizada nesta categoria.")
        snapshots.append({
            "application_id": None,
            "application_name": None,
            "application_name_en": None,
            "component_name": None,
            "category_code": category.code,
            "category_name": category.name,
            "optional_id": str(optional.id),
            "optional_name": optional.color_name,
            "display_order": 10_000,
        })

    missing = [
        row.name for row in applications
        if row.required and row.id not in selected_application_ids
    ]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Selecione os opcionais obrigatórios: {', '.join(missing)}.",
        )

    snapshots.sort(key=lambda row: (
        row["display_order"], row["category_code"],
        row["application_id"] or "", row["optional_id"],
    ))
    canonical = [{
        "application_id": row["application_id"],
        "category_code": row["category_code"],
        "optional_id": row["optional_id"],
    } for row in snapshots]
    if not canonical:
        return [], "base"
    key = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return snapshots, key


@router.post("/{box_id}/items", response_model=ShowroomBoxRead)
async def add_item(
    box_id: uuid.UUID,
    payload: ShowroomItemAdd,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    priced_product = (await db.execute(
        select(Product)
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
    configuration, configuration_key = await _optional_configuration(
        db, priced_product, payload.optional_choices,
    )
    upserted = (await db.execute(
        pg_insert(ShowroomBoxItem)
        .values(
            box_id=box.id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            optional_configuration=configuration,
            configuration_key=configuration_key,
        )
        .on_conflict_do_update(
            constraint="uq_showroom_box_items_configuration",
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
    return await _read_box(db, box, language)


@router.patch("/{box_id}/items/{item_id}", response_model=ShowroomBoxRead)
async def update_item(
    box_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ShowroomItemUpdate,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
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
    return await _read_box(db, box, language)


@router.delete("/{box_id}/items/{item_id}", response_model=ShowroomBoxRead)
async def remove_item(
    box_id: uuid.UUID,
    item_id: uuid.UUID,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
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
    return await _read_box(db, box, language)
