import uuid
from decimal import Decimal
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, func, literal_column, or_, select
from sqlalchemy.orm import load_only, noload

from app.api.deps import get_current_principal, get_db_session, get_current_user, is_client_account, require_roles
from app.models.client import Client
from app.models.product import Product, ProductSetItem, ProductSetComponent
from app.models.product_type import ProductType
from app.models.optional_color import OptionalColor
from app.models.user import User, UserRole
from app.models.market import ProductMarket, ProductPrice, PriceList
from app.core.markets import MarketPrincipal
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductRead,
    ProductSetItemRead, ProductSetComponentCreate, ProductSetComponentRead,
    ProductBatchRequest,
)
from app.core.config import settings
from app.core.search import literal_contains_pattern
from app.core.uploads import build_photo_url, build_thumbnail_url, delete_upload, persist_upload, sanitize_image_upload


def _normalized_product_type_value(value: str) -> str:
    """Chave tolerante a caixa, espaços e plural simples do tipo de produto."""
    normalized = value.strip().lower()
    return normalized[:-1] if normalized.endswith("s") else normalized


def _normalized_product_type_expression(column):
    """Equivalente PostgreSQL da normalização aplicada ao valor do filtro."""
    return func.regexp_replace(func.lower(func.btrim(column)), "s$", "")


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


async def _visible_price_profile(db: AsyncSession, user: User) -> Optional[str]:
    """Bloco 96: qual tabela de preço a role logada pode enxergar no catálogo.

    `None` = vê as duas (admin, produtos, cadastros, vendedor interno,
    representante e executivo). Conta de cliente-final vê apenas o preço do
    próprio perfil de faturamento — o preço da outra tabela nem sai da API.
    """
    if not is_client_account(user):
        return None
    if not user.linked_id:
        return "lojista"
    profile = (
        await db.execute(
            select(Client.price_profile).where(Client.id == user.linked_id)
        )
    ).scalar_one_or_none()
    return profile or "lojista"


def _to_read(product: Product, visible_profile: Optional[str] = None) -> ProductRead:
    data = ProductRead.model_validate(product)
    if visible_profile == "corporativo":
        data.price_lojista = None
        data.price = None  # coluna legada espelha o preço lojista (Bloco 62)
    elif visible_profile == "lojista":
        data.price_corporativo = None
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


async def _to_market_reads(
    db: AsyncSession,
    products: list[Product],
    principal: MarketPrincipal,
    visible_profile: Optional[str],
    language: Literal["pt-PT", "en-GB"] = "pt-PT",
) -> list[ProductRead]:
    market = principal.code
    context = principal.market
    ids = [product.id for product in products]
    rows = (await db.execute(
        select(ProductPrice.product_id, PriceList.code, ProductPrice.amount)
        .join(PriceList, PriceList.id == ProductPrice.price_list_id)
        .where(PriceList.market_code == market, PriceList.is_active.is_(True), ProductPrice.product_id.in_(ids))
    )).all() if ids else []
    prices: dict[uuid.UUID, dict[str, Decimal]] = {}
    for product_id, code, amount in rows:
        if visible_profile is None or visible_profile == code:
            prices.setdefault(product_id, {})[code] = amount
    localized_names: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    if market == "EU" and ids:
        localized_rows = (await db.execute(
            select(
                ProductMarket.product_id,
                ProductMarket.description_pt_pt,
                ProductMarket.description_en,
            ).where(
                ProductMarket.market_code == "EU",
                ProductMarket.product_id.in_(ids),
            )
        )).all()
        localized_names = {
            product_id: (description_pt_pt, description_en)
            for product_id, description_pt_pt, description_en in localized_rows
        }
    result = []
    for product in products:
        item = _to_read(product, visible_profile if market == "BR" else None)
        item.market_code = market
        item.currency = context.currency
        item.market_prices = prices.get(product.id, {})
        if market == "EU":
            descriptions = localized_names.get(product.id)
            if descriptions:
                item.description_pt_pt, item.description_en = descriptions
                translated_description = descriptions[1] if language == "en-GB" else descriptions[0]
                if translated_description:
                    item.description = translated_description
            item.price = item.market_prices.get(visible_profile or "lojista")
            item.price_lojista = item.market_prices.get("lojista")
            item.price_corporativo = item.market_prices.get("corporativo")
        result.append(item)
    return result


async def _resolve_set_items(
    db: AsyncSession, items: list, parent_code: str
) -> list[ProductSetItem]:
    codes = list(dict.fromkeys(item.product_code for item in items))
    products = (
        await db.execute(
            select(Product)
            .where(Product.product_code.in_(codes))
            .options(
                load_only(
                    Product.id,
                    Product.product_code,
                    Product.is_set,
                    Product.is_active,
                ),
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
        # Desativado é diferente de inexistente: a mensagem precisa dizer qual
        # dos dois, senão o operador procura um código que está lá.
        if not p.is_active:
            raise HTTPException(400, f"Produto '{item.product_code}' está desativado e não pode compor um conjunto.")
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
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    # Produto desativado (DELETE = desativação, Migration/01) sai do catálogo.
    # Entra em `filters`, então vale também para a contagem do X-Total-Count.
    active_market = principal.code
    filters = [
        Product.is_active.is_(True),
        exists().where(
            ProductMarket.product_id == Product.id,
            ProductMarket.market_code == active_market,
            ProductMarket.is_available.is_(True),
        ),
    ]
    search = q.strip() if q else ""
    if search:
        search_pattern = literal_contains_pattern(search)
        localized_description = (
            ProductMarket.description_en if language == "en-GB"
            else ProductMarket.description_pt_pt
        )
        filters.append(
            or_(
                Product.product_code.ilike(search_pattern, escape="\\"),
                Product.description.ilike(search_pattern, escape="\\"),
                exists().where(
                    ProductMarket.product_id == Product.id,
                    ProductMarket.market_code == active_market,
                    localized_description.ilike(search_pattern, escape="\\"),
                ),
            )
        )
    if product_type:
        filters.append(
            _normalized_product_type_expression(Product.type)
            == _normalized_product_type_value(product_type)
        )
    if group_id:
        filters.append(
            _normalized_product_type_expression(Product.type).in_(
                select(_normalized_product_type_expression(ProductType.name)).where(
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
    visible_profile = await _visible_price_profile(db, current_user)
    return await _to_market_reads(db, products, principal, visible_profile, language)


@router.post("/batch", response_model=List[ProductRead])
async def get_products_batch(
    payload: ProductBatchRequest,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    codes = list(dict.fromkeys(payload.product_codes))
    products = (
        await db.execute(
            select(Product).where(
                Product.product_code.in_(codes),
                Product.is_active.is_(True),
                exists().where(
                    ProductMarket.product_id == Product.id,
                    ProductMarket.market_code == principal.code,
                    ProductMarket.is_available.is_(True),
                ),
            )
        )
    ).scalars().all()
    product_map = {product.product_code: product for product in products}
    visible_profile = await _visible_price_profile(db, current_user)
    ordered = [product_map[code] for code in codes if code in product_map]
    return await _to_market_reads(db, ordered, principal, visible_profile, language)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.code != "BR":
        raise HTTPException(status_code=403, detail="O catálogo-base é mantido no mercado Brasil; use a importação europeia para disponibilidade e preços.")
    holder_is_active = (
        await db.execute(
            select(Product.is_active).where(Product.product_code == payload.product_code)
        )
    ).scalar_one_or_none()
    if holder_is_active is not None:
        # Opção A (decisão do Alto Comando, 05/08/2026): o código segue
        # reservado por um produto desativado. Sem dizer isso, o operador vê
        # "já existe" para um código que não aparece em lugar nenhum.
        detail = (
            f"Código '{payload.product_code}' já existe."
            if holder_is_active
            else (
                f"Código '{payload.product_code}' pertence a um produto "
                "desativado e segue reservado."
            )
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    product_data = payload.model_dump(exclude={"optional_ids", "set_items", "components"})
    product = Product(**product_data)
    product.optionals = await _resolve_optionals(db, payload.optional_ids)
    if payload.is_set:
        product.set_items = await _resolve_set_items(db, payload.set_items, payload.product_code)
    if _is_conjunto_type(payload.type) and payload.components:
        product.components = await _resolve_components(db, payload.components)
    db.add(product)
    await db.flush()
    db.add(ProductMarket(product_id=product.id, market_code="BR", is_available=True))
    lists = (await db.execute(select(PriceList).where(PriceList.market_code == "BR"))).scalars().all()
    amounts = {"lojista": payload.price_lojista, "corporativo": payload.price_corporativo}
    for price_list in lists:
        if price_list.code in amounts:
            db.add(ProductPrice(product_id=product.id, price_list_id=price_list.id, amount=amounts[price_list.code]))
    await db.commit()
    await db.refresh(product)
    return _to_read(product)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ANY,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
            exists().where(
                ProductMarket.product_id == Product.id,
                ProductMarket.market_code == principal.code,
                ProductMarket.is_available.is_(True),
            ),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return (await _to_market_reads(db, [product], principal, await _visible_price_profile(db, current_user), language))[0]


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(Product).where(
        Product.id == product_id,
        Product.is_active.is_(True),
        exists().where(
            ProductMarket.product_id == Product.id,
            ProductMarket.market_code == principal.code,
            ProductMarket.is_available.is_(True),
        ),
    ))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")

    if principal.code == "EU":
        price_changes = {
            "lojista": payload.price_lojista,
            "corporativo": payload.price_corporativo,
            "pvp": payload.price_pvp,
        }
        translation_changes = {
            "description_pt_pt": payload.description_pt_pt,
            "description_en": payload.description_en,
        }
        if not any(amount is not None for amount in price_changes.values()) and not any(translation_changes.values()):
            raise HTTPException(
                status_code=422,
                detail="Informe ao menos um nome localizado ou preço em EUR para atualizar.",
            )
        price_lists = (await db.execute(select(PriceList).where(
            PriceList.market_code == "EU",
            PriceList.is_active.is_(True),
        ))).scalars().all()
        lists_by_code = {price_list.code: price_list for price_list in price_lists}
        if any(code not in lists_by_code for code in price_changes):
            raise HTTPException(
                status_code=422,
                detail="As listas Lojista, Corporativo e PVP não estão configuradas em Portugal.",
            )
        for code, amount in price_changes.items():
            if amount is None:
                continue
            price_list = lists_by_code[code]
            existing_price = (await db.execute(select(ProductPrice).where(
                ProductPrice.product_id == product.id,
                ProductPrice.price_list_id == price_list.id,
            ))).scalar_one_or_none()
            if existing_price:
                existing_price.amount = amount
            else:
                db.add(ProductPrice(
                    product_id=product.id,
                    price_list_id=price_list.id,
                    amount=amount,
                ))
        if any(value is not None for value in translation_changes.values()):
            localized = (await db.execute(select(ProductMarket).where(
                ProductMarket.product_id == product.id,
                ProductMarket.market_code == "EU",
            ))).scalar_one()
            for field, value in translation_changes.items():
                if value is not None:
                    setattr(localized, field, value.strip())
        await db.commit()
        await db.refresh(product)
        return (await _to_market_reads(
            db,
            [product],
            principal,
            await _visible_price_profile(db, current_user),
        ))[0]

    data = payload.model_dump(exclude_unset=True, exclude={"optional_ids", "set_items", "components"})
    data.pop("price_pvp", None)
    data.pop("description_pt_pt", None)
    data.pop("description_en", None)
    optional_ids = payload.optional_ids
    set_items_in = payload.set_items
    components_in = payload.components
    for field, value in data.items():
        setattr(product, field, value)
    product.source_version += 1
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
    lists = (await db.execute(select(PriceList).where(PriceList.market_code == "BR"))).scalars().all()
    price_changes = {"lojista": data.get("price_lojista"), "corporativo": data.get("price_corporativo")}
    for price_list in lists:
        if price_changes.get(price_list.code) is not None:
            existing_price = (await db.execute(select(ProductPrice).where(
                ProductPrice.product_id == product.id,
                ProductPrice.price_list_id == price_list.id,
            ))).scalar_one_or_none()
            if existing_price:
                existing_price.amount = price_changes[price_list.code]
            else:
                db.add(ProductPrice(product_id=product.id, price_list_id=price_list.id, amount=price_changes[price_list.code]))
    await db.commit()
    await db.refresh(product)
    return _to_read(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    result = await db.execute(select(Product).where(
        Product.id == product_id,
        Product.is_active.is_(True),
    ))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if principal.code == "EU":
        availability = (await db.execute(select(ProductMarket).where(
            ProductMarket.product_id == product_id,
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
        ))).scalar_one_or_none()
        if not availability:
            raise HTTPException(status_code=404, detail="Produto não encontrado.")
        availability.is_available = False
        await db.commit()
        return
    # Migration/01 + decisão do Alto Comando (05/08/2026): desativação, não
    # exclusão física. O product_code permanece reservado (Opção A) e a foto
    # não é apagada — o produto pode ser reativado no futuro.
    product.is_active = False
    product.source_version += 1
    await db.commit()


@router.post("/{product_id}/upload-photo", response_model=ProductRead)
async def upload_photo(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN_VENDEDOR,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.code != "BR":
        raise HTTPException(status_code=403, detail="Altere as fotos do catálogo-base no mercado Brasil.")
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
