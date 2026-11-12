"""Área de protótipos (mercado EU, só para quem tem a permissão).

Um protótipo é um produto EU (`products.is_prototype`) com código `PROT-xxxx`
gerado aqui, dono (`created_by_user_id`) e fora de qualquer lista comum. As
rotas reaproveitam os helpers do produto normal para que "criar protótipo" seja
igual a "criar produto": mesmos campos, preços por lista, nomes PT/EN, fotos e
opcionais. Tudo daqui exige `require_prototype_manager` (404 sem permissão) e só
enxerga protótipos do próprio usuário (ownership).
"""
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_prototype_manager
from app.api.price_access import visible_price_scope
from app.api.routers.products import (
    _create_product_for_market,
    _to_market_reads,
    _visible_price_profile,
    add_product_photo,
    remove_product_photo,
    reorder_product_photos,
    set_primary_product_photo,
    update_product,
)
from app.core.markets import MarketPrincipal
from app.core.search import literal_contains_pattern
from app.models.market import ProductMarket, VAT_APPROVED, VAT_SOURCE_PROTOTYPE
from app.models.optional_application import ProductOptionalApplication
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.product import Product, format_prototype_code, prototype_code_seq
from app.schemas.product import ProductCreate, ProductPhotosOrder, ProductRead, ProductUpdate
from app.schemas.prototype import (
    PrototypeCreate,
    PrototypeOptionalGroupRead,
    PrototypeOptionalGroupWrite,
    PrototypeOptionRead,
    PrototypeUpdate,
)

router = APIRouter(prefix="/api/v1/prototypes", tags=["prototypes"])

_MANAGER = Depends(require_prototype_manager)


def _ownership_filters(principal: MarketPrincipal) -> list:
    """Dono: só os próprios. Admin: todos (regra única em `MarketActor`)."""
    return [] if principal.actor.sees_all_prototypes else [Product.created_by_user_id == principal.user.id]


async def _own_prototype(
    db: AsyncSession, principal: MarketPrincipal, prototype_id: uuid.UUID
) -> Product:
    """Protótipo ativo do próprio usuário (o admin alcança o de qualquer um);
    qualquer outro caso é 404."""
    product = (await db.execute(select(Product).where(
        Product.id == prototype_id,
        Product.market_code == principal.code,
        Product.is_prototype.is_(True),
        *_ownership_filters(principal),
        Product.is_active.is_(True),
    ))).scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Protótipo não encontrado.")
    return product


async def _read_one(
    db: AsyncSession,
    product: Product,
    principal: MarketPrincipal,
    language: Literal["pt-PT", "en-GB"] = "pt-PT",
) -> ProductRead:
    price_scope = await visible_price_scope(db, principal.actor, principal.code)
    return (await _to_market_reads(
        db, [product], principal,
        await _visible_price_profile(db, principal.actor), language, price_scope,
    ))[0]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_prototype(
    payload: PrototypeCreate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    # nextval é atômico: duas criações simultâneas nunca recebem o mesmo número.
    number = (await db.execute(select(prototype_code_seq.next_value()))).scalar_one()
    product_payload = ProductCreate(
        product_code=format_prototype_code(number),
        description=payload.description_pt_pt,
        description_pt_pt=payload.description_pt_pt,
        description_en=payload.description_en,
        summary=payload.summary,
        type=payload.type,
        catalog_id=payload.catalog_id,
        is_circular=payload.is_circular,
        altura=payload.altura,
        largura=payload.largura,
        profundidade=payload.profundidade,
        price_lojista=payload.price_lojista,
        price_corporativo=payload.price_corporativo,
        price_pvp=payload.price_pvp,
        price_arquiteto=payload.price_arquiteto,
        observacao=payload.observacao,
        optional_ids=payload.optional_ids,
        optional_applications=payload.optional_applications,
    )
    product = await _create_product_for_market(
        product_payload, db, principal.code,
        prototype_owner_id=principal.user.id,
        prototype_vat_rate=payload.vat_rate,
    )
    return await _read_one(db, product, principal)


@router.get("", response_model=List[ProductRead])
async def list_prototypes(
    response: Response,
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=100, ge=1, le=500),
    q: Optional[str] = Query(default=None, max_length=200),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    """Meus protótipos ativos (os mais novos primeiro por padrão); o admin vê os de todos."""
    filters = [
        Product.market_code == principal.code,
        Product.is_prototype.is_(True),
        *_ownership_filters(principal),
        Product.is_active.is_(True),
    ]
    search = q.strip() if q else ""
    if search:
        pattern = literal_contains_pattern(search)
        filters.append(or_(
            Product.product_code.ilike(pattern, escape="\\"),
            Product.description.ilike(pattern, escape="\\"),
            Product.summary.ilike(pattern, escape="\\"),
            exists().where(
                ProductMarket.product_id == Product.id,
                ProductMarket.market_code == principal.code,
                or_(
                    ProductMarket.description_pt_pt.ilike(pattern, escape="\\"),
                    ProductMarket.description_en.ilike(pattern, escape="\\"),
                ),
            ),
        ))
    total = (await db.execute(
        select(func.count()).select_from(Product).where(*filters)
    )).scalar_one()
    order = Product.product_code.desc() if sort_dir == "desc" else Product.product_code.asc()
    products = list((await db.execute(
        select(Product).where(*filters).order_by(order, Product.id).offset(skip).limit(limit)
    )).scalars().all())
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if skip + len(products) < total else "false"
    response.headers["X-Page-Size"] = str(len(products))
    price_scope = await visible_price_scope(db, principal.actor, principal.code)
    return await _to_market_reads(
        db, products, principal,
        await _visible_price_profile(db, principal.actor), language, price_scope,
    )


@router.get("/{prototype_id}", response_model=ProductRead)
async def get_prototype(
    prototype_id: uuid.UUID,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    product = await _own_prototype(db, principal, prototype_id)
    return await _read_one(db, product, principal, language)


@router.patch("/{prototype_id}", response_model=ProductRead)
async def update_prototype(
    prototype_id: uuid.UUID,
    payload: PrototypeUpdate,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    product = await _own_prototype(db, principal, prototype_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe ao menos um campo para atualizar.")
    vat_rate = data.pop("vat_rate", None)
    if vat_rate is not None:
        market_row = (await db.execute(select(ProductMarket).where(
            ProductMarket.product_id == product.id,
            ProductMarket.market_code == principal.code,
        ))).scalar_one()
        market_row.vat_rate = vat_rate
        market_row.vat_status = VAT_APPROVED
        market_row.vat_source = VAT_SOURCE_PROTOTYPE
        market_row.approved_by_user_id = principal.user.id
        market_row.approved_at = datetime.now(timezone.utc)
    if "description_pt_pt" in data:
        data["description"] = data["description_pt_pt"]
    if data:
        # Mesmo caminho da edição de produto EU (preços por lista, nomes PT/EN,
        # opcionais, validações de tipo/catálogo e medidas).
        return await update_product(
            product.id, ProductUpdate(**data),
            db=db, current_user=principal.actor, principal=principal,
        )
    product.source_version += 1
    await db.commit()
    await db.refresh(product)
    return await _read_one(db, product, principal)


@router.delete("/{prototype_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prototype(
    prototype_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    """Desativa o protótipo. O código fica reservado: nunca é reaproveitado, e
    orçamentos que já o usam seguem legíveis (snapshot)."""
    product = await _own_prototype(db, principal, prototype_id)
    availability = (await db.execute(select(ProductMarket).where(
        ProductMarket.product_id == product.id,
        ProductMarket.market_code == principal.code,
    ))).scalar_one_or_none()
    if availability is not None:
        availability.is_available = False
    product.is_active = False
    product.source_version += 1
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{prototype_id}/photos", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def add_prototype_photo(
    prototype_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _own_prototype(db, principal, prototype_id)
    return await add_product_photo(
        prototype_id, file, db=db, current_user=principal.actor, principal=principal,
    )


@router.delete("/{prototype_id}/photos/{photo_id}", response_model=ProductRead)
async def remove_prototype_photo(
    prototype_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _own_prototype(db, principal, prototype_id)
    return await remove_product_photo(
        prototype_id, photo_id, db=db, current_user=principal.actor, principal=principal,
    )


@router.put("/{prototype_id}/photos/order", response_model=ProductRead)
async def reorder_prototype_photos(
    prototype_id: uuid.UUID,
    payload: ProductPhotosOrder,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _own_prototype(db, principal, prototype_id)
    return await reorder_product_photos(
        prototype_id, payload, db=db, current_user=principal.actor, principal=principal,
    )


@router.put("/{prototype_id}/photos/{photo_id}/primary", response_model=ProductRead)
async def set_primary_prototype_photo(
    prototype_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    await _own_prototype(db, principal, prototype_id)
    return await set_primary_product_photo(
        prototype_id, photo_id, db=db, current_user=principal.actor, principal=principal,
    )


# ── Grupos de opcionais que existem só neste protótipo ────────────────────────
# Um grupo local é uma categoria + opções com `prototype_id`. Nunca aparece nas
# listas gerais (negação por padrão no ORM). Para usá-lo, o protótipo recebe uma
# `optional_applications` apontando para o `id` do grupo, como com os grupos gerais.

_LOCAL_OPTION_BRAND = "IBTW"  # não é acabamento ILYA: aceita "Customizado"


def _slug(text_: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", "-", ascii_text).strip("-")[:20] or "GRUPO"


async def _group_read(db: AsyncSession, category: OptionalCategory) -> PrototypeOptionalGroupRead:
    options = (await db.execute(
        select(OptionalColor).where(
            OptionalColor.prototype_id == category.prototype_id,
            OptionalColor.category == category.code,
        ).order_by(OptionalColor.color_name, OptionalColor.id)
    )).scalars().all()
    return PrototypeOptionalGroupRead(
        id=category.id, code=category.code, name=category.name,
        options=[PrototypeOptionRead(id=o.id, name=o.color_name) for o in options],
    )


async def _own_group(
    db: AsyncSession, product: Product, category_id: uuid.UUID
) -> OptionalCategory:
    category = (await db.execute(select(OptionalCategory).where(
        OptionalCategory.id == category_id, OptionalCategory.prototype_id == product.id,
    ))).scalar_one_or_none()
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo de opcionais não encontrado.")
    return category


def _unique_names(options) -> None:
    names = [o.name.casefold() for o in options]
    if len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opções repetidas no grupo.")


@router.get("/{prototype_id}/optional-groups", response_model=List[PrototypeOptionalGroupRead])
async def list_prototype_optional_groups(
    prototype_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    product = await _own_prototype(db, principal, prototype_id)
    categories = (await db.execute(
        select(OptionalCategory).where(OptionalCategory.prototype_id == product.id)
        .order_by(OptionalCategory.name, OptionalCategory.id)
    )).scalars().all()
    return [await _group_read(db, c) for c in categories]


@router.post(
    "/{prototype_id}/optional-groups", response_model=PrototypeOptionalGroupRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_prototype_optional_group(
    prototype_id: uuid.UUID,
    payload: PrototypeOptionalGroupWrite,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    product = await _own_prototype(db, principal, prototype_id)
    _unique_names(payload.options)
    category = OptionalCategory(
        market_code=principal.code, prototype_id=product.id, name=payload.name,
        code=f"{product.product_code}-{_slug(payload.name)}-{uuid.uuid4().hex[:4].upper()}"[:50],
    )
    db.add(category)
    await db.flush()
    for option in payload.options:
        db.add(OptionalColor(
            market_code=principal.code, prototype_id=product.id, category=category.code,
            color_name=option.name, brand=_LOCAL_OPTION_BRAND,
        ))
    product.source_version += 1
    await db.commit()
    return await _group_read(db, category)


@router.put("/{prototype_id}/optional-groups/{category_id}", response_model=PrototypeOptionalGroupRead)
async def replace_prototype_optional_group(
    prototype_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: PrototypeOptionalGroupWrite,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    """Renomeia o grupo e reconcilia as opções: com `id` mantém, sem `id` cria,
    as que não vierem saem. Orçamentos já feitos guardam o nome (snapshot)."""
    product = await _own_prototype(db, principal, prototype_id)
    category = await _own_group(db, product, category_id)
    _unique_names(payload.options)
    existing = {o.id: o for o in (await db.execute(select(OptionalColor).where(
        OptionalColor.prototype_id == product.id, OptionalColor.category == category.code,
    ))).scalars().all()}
    kept: set[uuid.UUID] = set()
    for option in payload.options:
        if option.id is not None:
            row = existing.get(option.id)
            if row is None or option.id in kept:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Opção não pertence ao grupo.")
            row.color_name = option.name
            kept.add(row.id)
        else:
            db.add(OptionalColor(
                market_code=principal.code, prototype_id=product.id, category=category.code,
                color_name=option.name, brand=_LOCAL_OPTION_BRAND,
            ))
    for option_id, row in existing.items():
        if option_id not in kept:
            await db.delete(row)
    category.name = payload.name
    product.source_version += 1
    await db.commit()
    await db.refresh(category)
    return await _group_read(db, category)


@router.delete("/{prototype_id}/optional-groups/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prototype_optional_group(
    prototype_id: uuid.UUID,
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    """Apaga o grupo, suas opções e as aplicações do protótipo que o usam."""
    product = await _own_prototype(db, principal, prototype_id)
    category = await _own_group(db, product, category_id)
    await db.execute(delete(ProductOptionalApplication).where(
        ProductOptionalApplication.category_id == category.id
    ))
    await db.execute(delete(OptionalColor).where(
        OptionalColor.prototype_id == product.id, OptionalColor.category == category.code,
    ))
    await db.delete(category)
    product.source_version += 1
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
