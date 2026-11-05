import base64
import binascii
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, false, func, or_, select, text, tuple_
from sqlalchemy.orm import load_only, noload, selectinload

from app.api.deps import (
    get_db_session,
    get_current_principal,
    get_current_user,
    require_order_access,
    require_roles,
    is_client_account,
    is_internal_operator,
)
from app.api.catalog_access import CatalogScope, allows, order_catalog_scope
from app.api.price_access import ensure_price_visible, visible_price_scope
from app.core.lifecycle import touch_client_activity
from app.core.limiter import limiter
from app.core.config import settings
from app.models.catalog import Catalog
from app.core.search import literal_contains_pattern
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.moloni import MoloniExportJob
from app.services.moloni_jobs import enqueue_finalized_eu_order
from app.services.order_email_jobs import enqueue_order_emails
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.product import ProductSetComponent
from app.models.optional_color import OptionalColor, product_optionals
from app.models.optional_application import ProductOptionalApplication, OrderItemOptionalChoice
from app.models.product_type import ProductType
from app.models.user import User, UserRole
from app.models.market import ProductMarket, ProductPrice, PriceList, VAT_APPROVED
from app.core.markets import MarketPrincipal, require_launch_country
from app.core.vat_exemption import VAT_EXEMPTION_REASONS
from app.schemas.order import is_legacy_custom, OptionalChoiceCreate, OrderCopyRead, OrderCopyRequest, OrderCreate, OrderItemCreate, OrderRead, OrderListRead, OrderStageUpdate, OrderUpdate, OrderHistoryRead
from app.services.integration_events import enqueue_event
from app.services.area_products import area_from_dimensions, is_area_product

logger = logging.getLogger("ilya.orders")
router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")
_MAX_ORDER_TOTAL = Decimal("999999999999999999.99")
_EU_DISCOUNT_PRICE_LIST = "pvp"
_EU_PVP_ADMIN_MAX_DISCOUNT = Decimal("70.00")
_EU_PVP_REP_MAX_DISCOUNT = Decimal("10.00")


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: object) -> Decimal:
    return _decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _ensure_total_capacity(*values: Decimal) -> None:
    if any(abs(value) > _MAX_ORDER_TOTAL for value in values):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Valor total do pedido excede o limite financeiro permitido.",
        )


def _can_operate_order(current_user: User) -> bool:
    """Papéis que operam o ciclo de vida do pedido (editar/finalizar/cancelar).

    Operador interno de vendas, representante, produtos e admin. A conta de
    portal do cliente-final nunca opera pedido (SEC-02) — `is_internal_operator`
    já exclui o legado `vendedor`+`linked_id`. Exclusão segue exclusiva do admin.
    """
    return (
        current_user.role
        in {UserRole.admin, UserRole.representante, UserRole.produtos}
        or is_internal_operator(current_user)
    )


def _can_create_order(current_user: User) -> bool:
    """Papéis que podem iniciar um pedido.

    Admin, operador interno, representante e cliente final podem criar. O papel
    `produtos` é somente catálogo/leitura de pedidos e não participa de decisões
    comerciais. `is_client_account` inclui o legado `vendedor` com `linked_id`.
    """
    return (
        current_user.role in {UserRole.admin, UserRole.representante}
        or is_internal_operator(current_user)
        or is_client_account(current_user)
    )


def _ensure_can_set_vat_exemption(current_user: User) -> None:
    allowed = not is_client_account(current_user) and (
        current_user.role in {UserRole.admin, UserRole.representante}
        or is_internal_operator(current_user)
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Somente administrador, operador interno ou representante pode isentar o IVA.",
        )


def _resolve_vat_exemption(
    current_user: User,
    market_code: str,
    requested: bool | None,
    requested_code: str | None,
    current: tuple[bool, str | None],
) -> tuple[bool, str | None]:
    """Isenção de IVA do orçamento (só EU). Ausente mantém o estado atual.

    Marcar ou desmarcar a isenção é decisão de admin, operador interno ou
    representante; conta de cliente nunca altera. O motivo é obrigatório.
    """
    if requested is None:
        return current
    if requested is False:
        if current[0]:
            _ensure_can_set_vat_exemption(current_user)
        return False, None
    if market_code != "EU":
        raise HTTPException(status_code=422, detail="Isenção de IVA só existe em Portugal.")
    if requested_code not in VAT_EXEMPTION_REASONS:
        raise HTTPException(status_code=422, detail="Informe o motivo da isenção de IVA.")
    if current != (True, requested_code):
        _ensure_can_set_vat_exemption(current_user)
    return True, requested_code


def _apply_order_rep_assignment(current_user: User, payload: OrderCreate) -> None:
    """Fixa a autoria comercial sem transformar o administrador em representante."""
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O usuário representante não possui um registro de representante associado."
            )
        payload.rep_id = current_user.rep_id
        return
    fixed_rep_id = getattr(current_user, "order_rep_id", None)
    if (
        current_user.role == UserRole.admin
        and payload.supersedes_order_id is None
        and fixed_rep_id is not None
    ):
        payload.rep_id = fixed_rep_id


def _representative_cannot_access_order(
    current_user: User,
    order: Order,
) -> bool:
    """Compatibilidade para regras auxiliares; consultas usam o filtro SQL."""
    return (
        current_user.role == UserRole.representante
        and (
            current_user.rep_id is None
            or order.rep_id != current_user.rep_id
        )
    )


def _order_visibility_filters(current_user: User) -> list:
    """Aplica a carteira na consulta, antes de materializar o pedido.

    Assim UUID e códigos conhecidos de outra carteira têm o mesmo resultado de
    um pedido inexistente. Contas legadas `vendedor`+`linked_id` seguem a regra
    de cliente final.
    """
    if current_user.role == UserRole.representante:
        return [
            Order.rep_id == current_user.rep_id
            if current_user.rep_id is not None
            else false()
        ]
    if is_client_account(current_user):
        return [
            Order.client_id == current_user.linked_id
            if current_user.linked_id is not None
            else false()
        ]
    return []


# Nome gravado na escolha customizada. custom_text marca a escolha: vazio na
# opção atual, com texto nos pedidos feitos quando havia a caixa de descrição.
CUSTOM_OPTIONAL_NAME = "Customizado"
# A opção "Customizado" existe só em Portugal; no Brasil o pedido usa apenas
# opcionais do cadastro.
CUSTOM_OPTION_MARKET = "EU"
CUSTOM_ILYA_DETAIL = "A opção Customizado não está disponível para acabamentos ILYA."


def _choice_snapshot(item: OrderItem) -> list[dict]:
    return [
        {
            "application_name": choice.application_name,
            "application_name_en": choice.application_name_en,
            "category_code": choice.category_code,
            "category_name": choice.category_name,
            "optional_name": choice.optional_name,
            "custom_text": choice.custom_text,
            "component_name": choice.component_name,
            "display_order": choice.display_order,
        }
        for choice in sorted(getattr(item, "optional_choices", []), key=lambda row: (row.display_order, str(row.id)))
    ]


def _items_history_snapshot(items: list[OrderItem]) -> list[dict]:
    # Termos financeiros como string decimal: o JSON não aceita Decimal e float
    # perderia exatidão. Cada versão do histórico fica reconstituível.
    return [
        {"product_code": item.product_code, "is_special": getattr(item, "is_special", False),
         "special_code": getattr(item, "special_code", None),
         "special_percent": None if getattr(item, "special_percent", None) is None else str(item.special_percent),
         "legacy_optionals": item.opt_categories,
         "applications": _choice_snapshot(item), "comment": item.comment,
         **{field: str(_decimal(getattr(item, field)))
            for field in ("qty", "unit_price", "discount", "ipi_rate", "ipi_value")},
         "tax_label": item.tax_label, "currency": item.currency,
         **_rug_snapshot(item)} for item in items
    ]


def _rug_snapshot(item: OrderItem) -> dict:
    # Tapete: qty é o total em m²; medida e peças explicam como ele foi formado.
    if not getattr(item, "sold_by_area", False):
        return {}
    width_m, depth_m = item.area_width_m, item.area_depth_m
    return {
        "area_width_m": None if width_m is None else str(width_m),
        "area_depth_m": None if depth_m is None else str(depth_m),
        "area_pieces": item.area_pieces or 1,
    }


async def _batch_load_optional_slots(
    db: AsyncSession, products: list[Product],
) -> tuple[
    dict[uuid.UUID, list[ProductOptionalApplication]],
    dict[uuid.UUID, set[str]],
]:
    if not products:
        return {}, {}

    product_ids = [product.id for product in products]
    applications = (
        await db.execute(
            select(ProductOptionalApplication)
            .where(ProductOptionalApplication.product_id.in_(product_ids))
            .options(selectinload(ProductOptionalApplication.category))
        )
    ).scalars().all()

    applications_by_product_id: dict[
        uuid.UUID, list[ProductOptionalApplication]
    ] = {}
    for application in applications:
        applications_by_product_id.setdefault(
            application.product_id, []
        ).append(application)

    direct_pairs = (
        await db.execute(
            select(product_optionals.c.product_id, OptionalColor.category)
            .join(
                OptionalColor,
                product_optionals.c.optional_id == OptionalColor.id,
            )
            .where(product_optionals.c.product_id.in_(product_ids))
        )
    ).all()

    direct_by_product_id: dict[uuid.UUID, set[str]] = {}
    for product_id, category in direct_pairs:
        direct_by_product_id.setdefault(product_id, set()).add(category)

    legacy_categories_by_product_id: dict[uuid.UUID, set[str]] = {}
    for product in products:
        application_categories = {
            application.category.code
            for application in applications_by_product_id.get(product.id, [])
        }
        declared_categories = {
            category.strip()
            for category in (product.all_optionals_categories or "").split(",")
            if category.strip()
        }
        legacy_categories_by_product_id[product.id] = (
            direct_by_product_id.get(product.id, set()) | declared_categories
        ) - application_categories

    return applications_by_product_id, legacy_categories_by_product_id


def _missing_optional_labels(
    applications: list[ProductOptionalApplication],
    expected_legacy_categories: set[str],
    selected_application_ids: set[uuid.UUID],
    opt_categories: dict | None,
) -> list[str]:
    missing = [
        application.name
        for application in applications
        if application.id not in selected_application_ids
    ]
    selected_legacy_categories = {
        category
        for category, value in (opt_categories or {}).items()
        if value is not None and str(value).strip()
    }
    missing.extend(sorted(
        expected_legacy_categories - selected_legacy_categories
    ))
    return missing


async def _resolve_item_choices(
    db: AsyncSession, product: Product, market_code: str, item_in: OrderItemCreate,
    source: OrderItem | None = None,
    require_complete: bool = True,
) -> list[OrderItemOptionalChoice]:
    if market_code != CUSTOM_OPTION_MARKET and (
        any(row.custom_text is not None for row in item_in.optional_choices)
        or any(is_legacy_custom(value) for value in item_in.opt_categories.values())
    ):
        raise HTTPException(status_code=422, detail="A opção Customizado só está disponível em Portugal.")
    # An unchanged historical line is copied as a snapshot, even if the master
    # application or optional was removed after the original order.
    if source is not None and source.product_code == item_in.product_code and source.opt_categories == item_in.opt_categories:
        old_pairs = {(row.application_id, row.optional_id, row.custom_text) for row in source.optional_choices}
        new_pairs = {(row.application_id, row.optional_id, row.custom_text) for row in item_in.optional_choices}
        if item_in.preserve_optional_choices or "optional_choices" not in item_in.model_fields_set or new_pairs == old_pairs:
            return [OrderItemOptionalChoice(
                id=uuid.uuid4(), application_id=row.application_id,
                optional_id=row.optional_id, application_name=row.application_name,
                application_name_en=row.application_name_en,
                category_code=row.category_code, category_name=row.category_name,
                optional_name=row.optional_name, custom_text=row.custom_text,
                component_name=row.component_name, display_order=row.display_order,
            ) for row in source.optional_choices]

    (
        applications_by_product_id,
        legacy_categories_by_product_id,
    ) = await _batch_load_optional_slots(db, [product])
    applications = applications_by_product_id.get(product.id, [])
    application_map = {row.id: row for row in applications}
    category_codes = {row.category.code for row in applications}
    if category_codes.intersection(item_in.opt_categories):
        raise HTTPException(status_code=422, detail="Categoria convertida deve usar aplicações, não o seletor antigo.")
    # Acabamento ILYA não é personalizado: seletor com algum opcional ILYA não
    # aceita "Customizado". O que já estava na linha original continua valendo.
    same_product = source is not None and source.product_code == item_in.product_code
    legacy_custom = set() if same_product and source.opt_categories == item_in.opt_categories else {
        category for category, value in item_in.opt_categories.items() if is_legacy_custom(value)
    }
    ilya_categories: set[str] = set()
    if legacy_custom or any(row.custom_text is not None for row in item_in.optional_choices):
        ilya_categories = set((await db.execute(select(OptionalColor.category).where(
            OptionalColor.market_code == market_code, OptionalColor.brand == "ILYA",
        ).distinct())).scalars())
    if legacy_custom:
        # O seletor antigo lista os opcionais do produto, ou todos os do
        # mercado nas categorias livres.
        free = (await db.execute(select(Product.all_optionals_categories).where(Product.id == product.id))).scalar_one()
        free_categories = set(filter(None, (free or "").split(",")))
        product_ilya = set((await db.execute(
            select(OptionalColor.category)
            .join(product_optionals, product_optionals.c.optional_id == OptionalColor.id)
            .where(product_optionals.c.product_id == product.id, OptionalColor.brand == "ILYA")
        )).scalars())
        blocked = sorted(category for category in legacy_custom
                         if category in (ilya_categories if category in free_categories else product_ilya))
        if blocked:
            raise HTTPException(status_code=422, detail=f"{CUSTOM_ILYA_DETAIL} ({', '.join(blocked)})")
    kept_custom = {row.application_id for row in source.optional_choices if row.custom_text is not None} if same_product else set()
    chosen = {row.application_id: row for row in item_in.optional_choices}
    if len(chosen) != len(item_in.optional_choices) or any(app_id not in application_map for app_id in chosen):
        raise HTTPException(status_code=422, detail="Aplicação inválida ou repetida neste produto.")
    option_ids = {row.optional_id for row in chosen.values() if row.optional_id is not None}
    optionals = (await db.execute(select(OptionalColor).where(
        OptionalColor.id.in_(option_ids), OptionalColor.market_code == market_code,
    ))).scalars().all() if option_ids else []
    option_map = {row.id: row for row in optionals}
    if len(option_map) != len(option_ids):
        raise HTTPException(status_code=422, detail="Opcional não existe neste mercado.")
    component_ids = {row.component_id for row in applications if row.component_id is not None}
    components = (await db.execute(select(ProductSetComponent).where(
        ProductSetComponent.id.in_(component_ids), ProductSetComponent.set_id == product.id,
    ))).scalars().all() if component_ids else []
    component_map = {row.id: row for row in components}
    if len(component_map) != len(component_ids):
        raise HTTPException(status_code=422, detail="Componente inválido na aplicação.")
    used: dict[tuple[str, uuid.UUID], ProductOptionalApplication] = {}
    result = []
    for app_id, choice in chosen.items():
        app = application_map[app_id]
        component_name = component_map[app.component_id].description if app.component_id else None
        if choice.custom_text is not None:
            # "Customizado" não consome opcional do cadastro, então não passa
            # pela lista de permitidos nem pela regra de repetição.
            has_ilya = app.category.code in ilya_categories if app.allow_all else any(
                row.brand == "ILYA" for row in app.allowed_optionals
            )
            if has_ilya and app_id not in kept_custom:
                raise HTTPException(status_code=422, detail=f"{CUSTOM_ILYA_DETAIL} ({app.name})")
            result.append(OrderItemOptionalChoice(
                id=uuid.uuid4(), application_id=app.id, optional_id=None,
                application_name=app.name, application_name_en=app.name_en,
                category_code=app.category.code, category_name=app.category.name,
                optional_name=CUSTOM_OPTIONAL_NAME, custom_text=choice.custom_text,
                component_name=component_name, display_order=app.display_order,
            ))
            continue
        optional_id = choice.optional_id
        optional = option_map[optional_id]
        if optional.category != app.category.code or (not app.allow_all and optional_id not in {row.id for row in app.allowed_optionals}):
            raise HTTPException(status_code=422, detail=f"Opção não autorizada em '{app.name}'.")
        key = (app.category.code, optional_id)
        if key in used and (not app.allow_repeat or not used[key].allow_repeat):
            raise HTTPException(status_code=422, detail=f"Opção repetida na categoria '{app.category.name}'.")
        used[key] = app
        result.append(OrderItemOptionalChoice(
            id=uuid.uuid4(), application_id=app.id, optional_id=optional.id,
            application_name=app.name, application_name_en=app.name_en,
            category_code=app.category.code, category_name=app.category.name,
            optional_name=optional.color_name,
            component_name=component_name,
            display_order=app.display_order,
        ))
    missing_labels = _missing_optional_labels(
        applications,
        legacy_categories_by_product_id.get(product.id, set()),
        set(chosen),
        item_in.opt_categories,
    )
    # Portugal salva o orçamento com opcionais pendentes; a exigência vale na
    # finalização (finalize_order). O Brasil continua exigindo ao salvar.
    if missing_labels and require_complete:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Selecione todos os opcionais para o produto "
                f"'{item_in.product_code}': {', '.join(missing_labels)}."
            ),
        )
    return result


async def _next_codes(
    db: AsyncSession,
    number_owner_id: uuid.UUID,
    market_code: str,
) -> tuple[str, str, int]:
    # O UPSERT bloqueia atomicamente apenas o contador deste usuário e não
    # reutiliza números de pedidos apagados. O ORC segue na sequence global.
    order_number = (
        await db.execute(
            text(
                """
                INSERT INTO market_order_counters (
                    market_code, number_owner_id,
                    next_value
                )
                VALUES (:market_code, :number_owner_id, 2)
                ON CONFLICT (market_code, number_owner_id) DO UPDATE
                SET
                    next_value = market_order_counters.next_value + 1,
                    updated_at = NOW()
                RETURNING next_value - 1
                """
            ),
            {"market_code": market_code, "number_owner_id": str(number_owner_id)},
        )
    ).scalar_one()
    orc_number = (
        await db.execute(
            text("""
                INSERT INTO market_quote_counters (market_code,next_value)
                VALUES (:market_code, 2)
                ON CONFLICT (market_code) DO UPDATE
                SET next_value=market_quote_counters.next_value+1, updated_at=NOW()
                RETURNING next_value-1
            """),
            {"market_code": market_code},
        )
    ).scalar_one()
    return (
        f"PED-{order_number:04d}",
        f"ORC-{orc_number:04d}",
        order_number,
    )


def _encode_order_cursor(created_at: datetime, order_id: uuid.UUID) -> str:
    timestamp = created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    raw = f"{timestamp.isoformat()}|{order_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_order_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        timestamp_raw, order_id_raw = raw.split("|", 1)
        timestamp = datetime.fromisoformat(timestamp_raw)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp, uuid.UUID(order_id_raw)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(status_code=422, detail="Cursor de paginação inválido.")


async def _load_products_and_types(
    db: AsyncSession,
    codes: list[str],
    market_code: str,
    *,
    allow_inactive_codes: set[str] | None = None,
) -> tuple[dict[str, Product], dict[str, ProductType]]:
    """Carrega produtos e seus tipos em 2 queries (evita N+1 por item — V-B1)."""
    activity_filter = Product.is_active.is_(True)
    if allow_inactive_codes:
        activity_filter = or_(
            activity_filter,
            Product.product_code.in_(allow_inactive_codes),
        )
    products = (await db.execute(
        select(Product)
        .where(
            Product.market_code == market_code,
            Product.product_code.in_(codes),
            activity_filter,
        )
        .options(
            load_only(
                Product.id,
                Product.product_code,
                Product.catalog_id,
                Product.area_limit_enabled,
                Product.max_area_m2,
                Product.description,
                Product.type,
                Product.is_circular,
                Product.altura,
                Product.largura,
                Product.profundidade,
                Product.all_optionals_categories,
                Product.price_lojista,
                Product.price_corporativo,
                Product.observacao,
            ),
            noload(Product.optionals),
            noload(Product.set_items),
            noload(Product.components),
        )
    )).scalars().all()
    product_map = {p.product_code: p for p in products}

    type_names = {p.type for p in products}
    types = (await db.execute(
        select(ProductType)
        .where(
            ProductType.name.in_(type_names),
            ProductType.market_code == market_code,
        )
        .options(selectinload(ProductType.group))
    )).scalars().all() if type_names else []
    type_map = {t.name: t for t in types}
    return product_map, type_map


def _ensure_catalogs_allowed(scope: CatalogScope, catalog_ids: set[uuid.UUID]) -> None:
    """Todo catálogo do pedido precisa estar liberado (MELH-07): senão 403."""
    if not all(allows(scope, catalog_id) for catalog_id in catalog_ids):
        raise HTTPException(
            status_code=403,
            detail="Catálogo não liberado para este cliente ou representante.",
        )


async def _order_catalog(
    db: AsyncSession,
    products: list[Product],
    scope: CatalogScope,
) -> Catalog | None:
    """Valida os catálogos dos itens e devolve o catálogo do pedido.

    O pedido pode misturar catálogos; cada um deles passa pela permissão do
    cliente/representante. Devolve o catálogo quando é um só e None quando o
    pedido mistura catálogos (orders.catalog_id fica vazio).
    """
    catalog_ids = {product.catalog_id for product in products}
    _ensure_catalogs_allowed(scope, catalog_ids)
    if len(catalog_ids) != 1:
        return None
    return (await db.execute(select(Catalog).where(Catalog.id == next(iter(catalog_ids))))).scalar_one()


async def _order_item_catalog_ids(db: AsyncSession, order: Order) -> set[uuid.UUID]:
    """Catálogos dos itens já gravados no pedido (pelo código do produto)."""
    if order.catalog_id is not None:
        return {order.catalog_id}
    codes = {item.product_code for item in order.items}
    if not codes:
        return set()
    return set((await db.execute(
        select(Product.catalog_id).where(
            Product.market_code == order.market_code,
            Product.product_code.in_(codes),
        )
    )).scalars().all())


def _price_for_profile(product: Product, profile: str) -> Decimal:
    """Preço faturado conforme o perfil do cliente (V-Bloco62)."""
    if profile == "corporativo":
        return _money(product.price_corporativo)
    return _money(product.price_lojista)


def _ensure_order_price_list_allowed(
    requested: str | None,
    client: Client,
    current: str | None = None,
) -> None:
    """Recusa tabela diferente da de faturamento do cliente, para qualquer papel.

    `current` é a tabela já gravada no pedido (ou na origem da revisão): pedido
    antigo feito com outra tabela continua editável sem trocar de tabela.
    """
    if requested is None or requested in {client.price_profile, current}:
        return
    raise HTTPException(
        status_code=422,
        detail=(
            f"O orçamento usa a tabela de preço do cliente ({client.price_profile}); "
            f"a tabela '{requested}' não pode ser escolhida."
        ),
    )


def _resolve_max_discount(
    current_user: User,
    client: Client,
    rep: Representative | None,
    market_code: str = "BR",
    price_list_code: str | None = None,
) -> Decimal:
    """Resolve o teto por tabela no EU (somente PVP) e por cadastro comercial no BR."""
    if market_code == "EU":
        code = (price_list_code or "").strip().lower()
        if code != _EU_DISCOUNT_PRICE_LIST:
            return _ZERO
        if is_client_account(current_user):
            return _ZERO
        if current_user.role == UserRole.admin:
            return _EU_PVP_ADMIN_MAX_DISCOUNT
        if current_user.role == UserRole.representante or is_internal_operator(current_user):
            return _EU_PVP_REP_MAX_DISCOUNT if rep else _ZERO
        return _ZERO
    if current_user.role == UserRole.representante:
        return _decimal(rep.max_discount) if rep else _ZERO
    if is_client_account(current_user):
        return _decimal(client.max_discount)
    if current_user.role == UserRole.vendedor:
        return _decimal(rep.max_discount) if rep else _decimal(client.max_discount)
    if current_user.role == UserRole.admin:
        return _HUNDRED
    # Papéis sem autorização comercial recebem zero por padrão. Isso evita que
    # uma nova role herde desconto integral ao cair neste fallback.
    return _ZERO


def _edit_line_max_discount(
    max_discount: Decimal,
    old_item: OrderItem | None,
    product_code: str,
    same_price_list: bool,
) -> Decimal:
    """Teto por linha na edição: mantém desconto antigo na mesma tabela/produto."""
    if old_item is not None and same_price_list and old_item.product_code == product_code:
        return max(_decimal(max_discount), _decimal(old_item.discount))
    return _decimal(max_discount)


def _resolve_eu_vat(
    product_code: str,
    vat_rate: Decimal | None,
    vat_status: str | None,
    group_rate: Decimal | None = None,
) -> Decimal:
    """Usa a taxa do SKU ou a taxa aprovada e uniforme de seu grupo EU."""
    if vat_status == VAT_APPROVED and vat_rate is not None:
        return _decimal(vat_rate)
    if group_rate is not None:
        return _decimal(group_rate)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Produto '{product_code}' não possui IVA aprovado no produto ou no grupo europeu.",
    )


async def _load_eu_group_vat_rates(
    db: AsyncSession, type_map: dict[str, ProductType]
) -> dict[uuid.UUID, Decimal]:
    """Taxa de grupo inferida apenas se os produtos aprovados concordarem."""
    group_ids = {type_.group_id for type_ in type_map.values() if type_.group_id}
    if not group_ids:
        return {}
    type_key = lambda col: func.regexp_replace(func.lower(func.btrim(col)), "s$", "")
    rows = (await db.execute(
        select(ProductType.group_id, ProductMarket.vat_rate)
        .select_from(ProductType)
        .join(Product, and_(
            Product.market_code == "EU",
            Product.is_active.is_(True),
            type_key(Product.type) == type_key(ProductType.name),
        ))
        .join(ProductMarket, and_(
            ProductMarket.product_id == Product.id,
            ProductMarket.market_code == "EU",
            ProductMarket.is_available.is_(True),
            ProductMarket.vat_status == VAT_APPROVED,
            ProductMarket.vat_rate.is_not(None),
        ))
        .where(ProductType.market_code == "EU", ProductType.group_id.in_(group_ids))
        .distinct()
    )).all()
    rates: dict[uuid.UUID, set[Decimal]] = {}
    for group_id, rate in rows:
        rates.setdefault(group_id, set()).add(_decimal(rate))
    return {group_id: next(iter(values)) for group_id, values in rates.items() if len(values) == 1}


def _resolve_br_ipi(product_code: str, product_type: ProductType | None) -> Decimal:
    """IPI faturável do Brasil, com a mesma recusa que o EU já tinha.

    O critério "sem IPI zero silencioso" do Checkpoint 06 valia só para o EU:
    aqui, tipo não encontrado caía para `_ZERO` e o pedido era emitido com
    imposto zerado, sem nada no log. `products.type` é texto livre (String(50),
    sem FK), então basta uma diferença de caixa — 'Banqueta' contra 'BANQUETA' —
    para o tipo não casar, e a conciliação de 06/10 achou 5 produtos assim.

    Zero legítimo continua passando: grupo com `ipi = 0` é cadastro, não
    ausência de dado. O que passa a ser recusado é a *falta* do vínculo — tipo
    inexistente no mercado, ou tipo sem grupo fiscal — porque aí não existe
    alíquota a aplicar, e zerar seria inventar uma.
    """
    if product_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Produto '{product_code}' tem tipo não cadastrado neste mercado; "
                "corrija o tipo do produto antes de usá-lo em pedido."
            ),
        )
    if product_type.group is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Produto '{product_code}' tem tipo '{product_type.name}' sem grupo "
                "fiscal, então não há alíquota de IPI definida."
            ),
        )
    return _decimal(product_type.group.ipi)


def _validate_discount(
    discount: Decimal | float,
    max_discount: Decimal | float,
    product_code: str,
) -> None:
    discount_value = _decimal(discount)
    max_discount_value = _decimal(max_discount)
    if discount_value < _ZERO or discount_value > max_discount_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Desconto de {discount_value}% no item '{product_code}' excede o limite permitido ({max_discount_value}%).",
        )


def _format_area(value: Decimal) -> str:
    """12.50 -> "12,5"; 10.00 -> "10" (mensagens em pt-BR)."""
    text_value = format(value.normalize(), "f")
    return text_value.replace(".", ",")


def _validate_item_quantity(product: Product, qty: Decimal) -> bool:
    """Valida a quantidade do item e devolve se ele é vendido por m².

    Tapete (catálogo "Tapete") aceita m² com até 2 casas e respeita o limite
    por item quando ligado no cadastro. Os demais produtos continuam em
    unidades inteiras — o tipo decimal da coluna não pode abrir brecha para
    vender 1,5 cadeira.
    """
    quantity = _decimal(qty)
    sold_by_area = is_area_product(product)
    if not sold_by_area:
        if quantity != quantity.to_integral_value():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"A quantidade do item '{product.product_code}' deve ser um número inteiro.",
            )
        return False
    if product.area_limit_enabled and product.max_area_m2 is not None:
        max_area = _decimal(product.max_area_m2)
        if quantity > max_area:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"O tapete '{product.product_code}' permite no máximo "
                    f"{_format_area(max_area)} m² por item."
                ),
            )
    return True


_MAX_RUG_TOTAL_AREA = Decimal("1000000")


def _checked_rug_total(item_in: OrderItemCreate, qty: Decimal) -> Decimal:
    """Área total (por peça × peças) precisa caber em order_items.qty, Numeric(10, 2)."""
    if qty > _MAX_RUG_TOTAL_AREA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"A área total do tapete '{item_in.product_code}' excede o limite permitido.",
        )
    return qty


def _resolve_item_measurement(
    product: Product,
    item_in: OrderItemCreate,
    source: OrderItem | None,
) -> tuple[Decimal, bool, Decimal | None, Decimal | None, int]:
    """Resolve qty, sold_by_area, dimensões e número de peças; tapete calcula área no servidor."""
    sold_by_area = is_area_product(product)
    if not sold_by_area:
        if item_in.area_width_m is not None or item_in.area_depth_m is not None or item_in.area_pieces is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"O item '{item_in.product_code}' não é vendido por área.",
            )
        if item_in.qty is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Informe a quantidade do item '{item_in.product_code}'.",
            )
        _validate_item_quantity(product, item_in.qty)
        return item_in.qty, False, None, None, 1
    if item_in.area_width_m is not None and item_in.area_depth_m is not None:
        width_m = _decimal(item_in.area_width_m)
        depth_m = _decimal(item_in.area_depth_m)
        pieces = item_in.area_pieces or 1
        raw_area = width_m * depth_m
        _validate_item_quantity(product, raw_area)
        qty = _checked_rug_total(item_in, area_from_dimensions(width_m, depth_m) * pieces)
        return qty, True, width_m, depth_m, pieces
    if (
        source is not None
        and source.product_code == item_in.product_code
        and source.sold_by_area
    ):
        area_per_piece = (_decimal(source.qty) / (source.area_pieces or 1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pieces = item_in.area_pieces if item_in.area_pieces is not None else (source.area_pieces or 1)
        qty = _checked_rug_total(item_in, area_per_piece * pieces)
        return qty, True, source.area_width_m, source.area_depth_m, pieces
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Informe largura × profundidade do tapete '{item_in.product_code}'.",
    )


def _calculate_order_line(
    *,
    unit_price: Decimal | float,
    qty: Decimal | int,
    discount: Decimal | float,
    max_discount: Decimal | float,
    product_code: str,
    tax_rate: Decimal | float,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Calcula a linha financeira usada igualmente na criação e na edição."""
    rounded_unit_price = _money(unit_price)
    decimal_discount = _decimal(discount)
    _validate_discount(decimal_discount, max_discount, product_code)
    effective_price = (
        rounded_unit_price * (_HUNDRED - decimal_discount) / _HUNDRED
    )
    subtotal = _money(_decimal(qty) * effective_price)
    decimal_tax_rate = _decimal(tax_rate)
    tax_value = _money(subtotal * decimal_tax_rate / _HUNDRED)
    return (
        rounded_unit_price,
        decimal_discount,
        subtotal,
        decimal_tax_rate,
        tax_value,
    )


_SPECIAL_CODE_RE = re.compile(r"^(?P<parent>.+)-E(?P<number>[1-9][0-9]*)$")


def _resolve_special_code(
    item_in: OrderItemCreate,
    parent_code: str,
    used_codes: set[str],
) -> str:
    """Valida o código estável enviado pelo cliente ou gera o próximo E livre."""
    if item_in.special_code is not None:
        match = _SPECIAL_CODE_RE.fullmatch(item_in.special_code)
        if not match or match.group("parent") != parent_code:
            raise HTTPException(status_code=422, detail="Código de especial inválido / Invalid special code.")
        code = item_in.special_code
        if code in used_codes:
            raise HTTPException(status_code=422, detail="Código de especial repetido no orçamento / Duplicate special code in quote.")
        used_codes.add(code)
        return code
    number = 1
    while f"{parent_code}-E{number}" in used_codes:
        number += 1
    code = f"{parent_code}-E{number}"
    used_codes.add(code)
    return code


def _calculate_special_order_line(
    *, base_price: Decimal | float, qty: Decimal | int, special_percent: Decimal,
    tax_rate: Decimal | float, product_code: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Calcula uma linha especial: percentagem livre, preço final gravado e desconto zero."""
    percent = _decimal(special_percent)
    if percent <= Decimal("-100") or percent > Decimal("1000"):
        raise HTTPException(status_code=422, detail="Percentagem especial fora do limite / Special percentage out of range.")
    unit_price = _money(_money(base_price) * (_HUNDRED + percent) / _HUNDRED)
    subtotal = _money(_decimal(qty) * unit_price)
    decimal_tax_rate = _decimal(tax_rate)
    tax_value = _money(subtotal * decimal_tax_rate / _HUNDRED)
    return unit_price, _ZERO, subtotal, decimal_tax_rate, tax_value


def _special_description(description: str) -> str:
    return f"ESPECIAL - {description}"


def _ensure_special_scope(current_user: User, market_code: str, items: list[OrderItemCreate]) -> None:
    if not any(item.is_special for item in items):
        return
    if market_code != "EU":
        raise HTTPException(status_code=422, detail="Itens especiais só estão disponíveis no mercado EU / Special items are only available in EU.")
    if is_client_account(current_user):
        raise HTTPException(status_code=403, detail="Contas de cliente não podem criar ou editar itens especiais / Client accounts cannot create or edit special items.")


def _ensure_special_comments(items: list[OrderItem], *, finalizing: bool = False) -> None:
    """Especial sem comentário não é salvo (422) nem vira pedido (409).

    O 409 da finalização continua valendo para orçamentos antigos, gravados
    quando salvar sem comentário ainda era permitido.
    """
    missing = [item.special_code or item.product_code for item in items if item.is_special and not (item.comment or "").strip()]
    if not missing:
        return
    codes = ", ".join(missing)
    if finalizing:
        raise HTTPException(
            status_code=409,
            detail=f"Itens especiais exigem comentário antes de finalizar: {codes} / Special items require a comment before finalization: {codes}",
        )
    raise HTTPException(
        status_code=422,
        detail=f"Itens especiais exigem comentário: {codes} / Special items require a comment: {codes}",
    )


async def _get_order(
    db: AsyncSession,
    id_or_code: str,
    current_user: User | None = None,
) -> Order:
    visibility = _order_visibility_filters(current_user) if current_user else []
    lookup_kind = "uuid"
    try:
        oid = uuid.UUID(id_or_code)
        result = await db.execute(select(Order).where(Order.id == oid, *visibility))
        order = result.scalar_one_or_none()
    except ValueError:
        upper = id_or_code.upper()
        if upper.startswith("ORC"):
            lookup_kind = "orc"
            result = await db.execute(
                select(Order).where(Order.orc_id == upper, *visibility)
            )
            order = result.scalar_one_or_none()
        else:
            lookup_kind = "code"
            result = await db.execute(
                select(Order).where(Order.code == upper, *visibility).limit(2)
            )
            matches = result.scalars().all()
            if len(matches) > 1:
                logger.warning(
                    "Busca de pedido ambígua: lookup=%s role=%s matches=%s",
                    lookup_kind,
                    current_user.role.value if current_user else "internal",
                    len(matches),
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Código de pedido ambíguo entre usuários. "
                        "Informe o código ORC ou o identificador do pedido."
                    ),
                )
            order = matches[0] if matches else None
    if not order:
        logger.info(
            "Pedido inacessível ou inexistente: lookup=%s role=%s",
            lookup_kind,
            current_user.role.value if current_user else "internal",
        )
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return order


async def _pending_optionals_by_item(
    db: AsyncSession, order: Order
) -> dict[uuid.UUID, list[str]]:
    """Opcionais ainda sem escolha em cada linha, por id da linha."""
    item_codes = [item.product_code for item in order.items]
    products = (
        await db.execute(
            select(Product).where(
                Product.market_code == order.market_code,
                Product.product_code.in_(item_codes),
            )
        )
    ).scalars().all() if item_codes else []
    products_by_code = {product.product_code: product for product in products}
    (
        applications_by_product_id,
        legacy_categories_by_product_id,
    ) = await _batch_load_optional_slots(db, products)
    pending: dict[uuid.UUID, list[str]] = {}
    for item in order.items:
        product = products_by_code.get(item.product_code)
        if product is None:
            continue
        missing_labels = _missing_optional_labels(
            applications_by_product_id.get(product.id, []),
            legacy_categories_by_product_id.get(product.id, set()),
            {
                choice.application_id
                for choice in item.optional_choices
                if choice.application_id is not None
            },
            item.opt_categories,
        )
        if missing_labels:
            pending[item.id] = missing_labels
    return pending


async def _annotate_pending_optionals(db: AsyncSession, order: Order) -> Order:
    """Expõe `pending_optionals` por linha em orçamentos EU ainda abertos."""
    if order.market_code != "EU" or order.is_finalized or order.is_cancelled:
        return order
    pending = await _pending_optionals_by_item(db, order)
    for item in order.items:
        item.pending_optionals = pending.get(item.id, [])
    return order


async def _reload_order_for_response(db, order_id) -> Order:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.optional_choices))
        .execution_options(populate_existing=True)
    )
    return await _annotate_pending_optionals(db, result.scalar_one())


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    order, skipped = await _create_order_core(payload, db, current_user, principal)
    if skipped:
        # Cópia: avisa os itens que a regra de cópia pulou (não é coluna do pedido).
        order.copy_skipped = skipped
    return order


async def _create_order_core(
    payload: OrderCreate,
    db: AsyncSession,
    current_user: User,
    principal: MarketPrincipal,
    *,
    copy_source: Order | None = None,
) -> tuple[Order, list[dict]]:
    """Cria o orçamento. Em modo cópia (`copy_source`) o item que não pode ser
    copiado (produto inativo, sem preço, fora do catálogo do cliente...) é
    pulado e devolvido em `skipped`; o desconto respeita o teto atual."""
    skipped: list[dict] = []
    if not _can_create_order(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação não permitida para o seu nível de acesso."
        )

    source_order: Order | None = None
    if payload.supersedes_order_id is not None:
        if not _can_operate_order(current_user):
            raise HTTPException(status_code=403, detail="Somente operador pode criar revisão de pedido finalizado.")
        source_order = (await db.execute(select(Order).where(
            Order.id == payload.supersedes_order_id,
            Order.market_code == principal.code,
            *_order_visibility_filters(current_user),
        ).with_for_update())).scalar_one_or_none()
        if source_order is None or source_order.client_id != payload.client_id:
            raise HTTPException(status_code=404, detail="Pedido de origem não encontrado neste mercado e cliente.")
        if not (source_order.is_finalized and not source_order.is_cancelled):
            raise HTTPException(status_code=409, detail="Revisão exige pedido de origem finalizado.")
        successor = (await db.execute(select(Order.id).where(
            Order.supersedes_order_id == source_order.id,
        ))).scalar_one_or_none()
        if successor is not None:
            raise HTTPException(status_code=409, detail="Este pedido já possui uma revisão. Revise a versão mais recente.")

    # Cópia: `copy_item_ids` None = todos os itens seguem a regra de cópia (endpoint
    # /copy, que monta os itens a partir da origem); um conjunto = só os itens que
    # ainda apontam para um item da origem (orçamento novo preenchido pela tela).
    copy_item_ids: set[uuid.UUID] | None = None
    if copy_source is None and payload.copy_source_order_id is not None:
        if payload.supersedes_order_id is not None:
            raise HTTPException(status_code=422, detail="Cópia e revisão não podem ser combinadas.")
        copy_source = (await db.execute(
            select(Order)
            .where(
                Order.id == payload.copy_source_order_id,
                Order.market_code == principal.code,
                *_order_visibility_filters(current_user),
            )
            .options(selectinload(Order.items))
        )).scalar_one_or_none()
        if copy_source is None:
            raise HTTPException(status_code=404, detail="Pedido de origem não encontrado.")
        copy_item_ids = {item.id for item in copy_source.items}
    copy_items = {item.id: item for item in copy_source.items} if copy_item_ids is not None else {}

    def is_copy_item(item_in: OrderItemCreate) -> bool:
        if copy_source is None:
            return False
        if copy_item_ids is None:
            return True
        origin = copy_items.get(item_in.source_order_item_id)
        return (
            origin is not None
            and origin.product_code == item_in.product_code
            and bool(origin.is_special) == bool(item_in.is_special)
            and (not item_in.is_special or origin.special_code == item_in.special_code)
        )

    _apply_order_rep_assignment(current_user, payload)

    if is_client_account(current_user) and payload.client_id != current_user.linked_id:
        # Cliente logado (V-Bloco66-RBAC): só pode criar pedido para si mesmo.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação não permitida para este cliente.")

    # Item especial novo (ou alterado) exige a permissão de sempre; só o item
    # herdado da origem na cópia dispensa essa checagem.
    _ensure_special_scope(
        current_user, principal.code, [item for item in payload.items if not is_copy_item(item)]
    )

    client = (await db.execute(select(Client).where(
        Client.id == payload.client_id,
        Client.market_code == principal.code,
    ))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    require_launch_country(principal.code, client.country)
    if is_client_account(current_user):
        # O vínculo comercial é definido pelo cadastro do cliente; a API não
        # aceita que uma conta de cliente atribua o pedido a outro representante.
        payload.rep_id = client.rep_id
    if (
        current_user.role == UserRole.representante
        and client.rep_id != current_user.rep_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Representante só pode criar pedidos para clientes vinculados a ele.",
        )

    rep: Representative | None = None
    if payload.rep_id:
        rep = (await db.execute(select(Representative).where(
            Representative.id == payload.rep_id,
            Representative.market_code == principal.code,
            Representative.relationship_ended_at.is_(None),
        ))).scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Representante não encontrado.")
        require_launch_country(principal.code, rep.country)

    # Batch-fetch de produtos e tipos — elimina N+1 (V-B1)
    product_map, type_map = await _load_products_and_types(
        db, [i.product_code for i in payload.items], principal.code
    )
    market_code = principal.code
    context = principal.market
    vat_exempt, vat_exemption_code = _resolve_vat_exemption(
        current_user, market_code, payload.vat_exempt, payload.vat_exemption_code,
        (source_order.vat_exempt, source_order.vat_exemption_code) if source_order else (False, None),
    )
    # Brasil fecha na tabela de faturamento do cliente. Em Portugal a tabela
    # é escolha livre do próprio orçamento, sem trava do cadastro.
    if market_code == "BR":
        _ensure_order_price_list_allowed(
            payload.price_list_code,
            client,
            source_order.price_list_code if source_order else None,
        )
    requested_price_list_code = client.price_profile
    if market_code == "EU":
        requested_price_list_code = (
            payload.price_list_code
            or (source_order.price_list_code if source_order else None)
            or client.price_profile
        )
    price_list_selector = (
        PriceList.code == requested_price_list_code
        if market_code == "EU"
        else PriceList.id == client.price_list_id
    )
    price_list = (await db.execute(
        select(PriceList).where(
            PriceList.market_code == market_code,
            price_list_selector,
            PriceList.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not price_list:
        raise HTTPException(
            status_code=422,
            detail=f"A tabela de preço '{requested_price_list_code}' não está disponível no mercado ativo.",
        )
    if market_code == "BR":
        ensure_price_visible(
            await visible_price_scope(db, current_user, principal.code),
            price_list.code,
        )
    max_discount = _resolve_max_discount(
        current_user, client, rep, market_code, price_list.code
    )
    product_ids = [product.id for product in product_map.values()]
    available_ids = set((await db.execute(
        select(ProductMarket.product_id).where(
            ProductMarket.market_code == market_code,
            ProductMarket.is_available.is_(True),
            ProductMarket.product_id.in_(product_ids),
        )
    )).scalars().all())
    price_map = dict((await db.execute(
        select(ProductPrice.product_id, ProductPrice.amount).where(
            ProductPrice.price_list_id == price_list.id,
            ProductPrice.product_id.in_(product_ids),
        )
    )).all())
    product_market_rows = (await db.execute(
        select(
            ProductMarket.product_id,
            ProductMarket.vat_rate,
            ProductMarket.vat_status,
            ProductMarket.description_pt_pt,
            ProductMarket.description_en,
        ).where(
            ProductMarket.market_code == market_code,
            ProductMarket.product_id.in_(product_ids),
        )
    )).all()
    product_vat = {
        row.product_id: (row.vat_rate, row.vat_status) for row in product_market_rows
    }
    group_vat = await _load_eu_group_vat_rates(db, type_map) if market_code == "EU" else {}
    localized_descriptions = {
        row.product_id: (row.description_pt_pt, row.description_en)
        for row in product_market_rows
    }

    total = _ZERO
    total_ipi = _ZERO
    order_items: list[OrderItem] = []
    source_items = {item.id: item for item in source_order.items} if source_order else {}
    used_special_codes: set[str] = set()
    catalog_scope = order_catalog_scope(current_user, client, rep)
    strict_items: list[OrderItem] = []
    for item_in in payload.items:
        lenient = is_copy_item(item_in)
        if item_in.is_special and is_client_account(current_user) and lenient:
            skipped.append({"product_code": item_in.product_code, "reason": "Conta de cliente não pode criar itens especiais / Client accounts cannot create special items."})
            continue
        if lenient:
            copy_product = product_map.get(item_in.product_code)
            skip_reason = None
            if copy_product is None:
                skip_reason = "Produto inativo ou fora do catálogo."
            elif copy_product.id not in available_ids:
                skip_reason = "Produto indisponível neste mercado."
            elif copy_product.id not in price_map:
                skip_reason = f"Produto sem preço na tabela {price_list.name}."
            elif not allows(catalog_scope, copy_product.catalog_id):
                skip_reason = "Produto fora do catálogo liberado para este cliente."
            if skip_reason:
                skipped.append({"product_code": item_in.product_code, "reason": skip_reason})
                continue
        try:
            product = product_map.get(item_in.product_code)
            if not product:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
            if product.id not in available_ids:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não está disponível neste mercado.")
            if product.id not in price_map:
                raise HTTPException(status_code=422, detail=f"Produto '{item_in.product_code}' não possui preço na lista {price_list.name}.")
            if (
                item_in.source_order_item_id
                and item_in.source_order_item_id not in source_items
                and item_in.source_order_item_id not in copy_items
            ):
                raise HTTPException(status_code=422, detail="Item de origem inválido para esta revisão.")
            optional_choices = await _resolve_item_choices(
                db, product, market_code, item_in,
                source_items.get(item_in.source_order_item_id),
                require_complete=market_code != "EU",
            )
            product_type = type_map.get(product.type)
            if market_code == "EU":
                vat_rate, vat_status = product_vat.get(product.id, (None, None))
                ipi_rate = _resolve_eu_vat(
                    product.product_code, vat_rate, vat_status,
                    group_vat.get(product_type.group_id) if product_type else None,
                )
            else:
                ipi_rate = _resolve_br_ipi(product.product_code, product_type)
            if vat_exempt:
                ipi_rate = _ZERO
            qty, sold_by_area, width_m, depth_m, area_pieces = _resolve_item_measurement(
                product, item_in, source_items.get(item_in.source_order_item_id)
            )
            special_code = None
            if item_in.is_special:
                special_code = _resolve_special_code(item_in, product.product_code, used_special_codes)
                unit_price, discount, subtotal, ipi_rate, ipi_value = _calculate_special_order_line(
                    base_price=price_map[product.id], qty=qty,
                    special_percent=item_in.special_percent, tax_rate=ipi_rate,
                    product_code=product.product_code,
                )
            else:
                unit_price, discount, subtotal, ipi_rate, ipi_value = _calculate_order_line(
                    unit_price=price_map[product.id], qty=qty,
                    discount=(min(item_in.discount or _ZERO, max_discount) if lenient else item_in.discount or _ZERO),
                    max_discount=max_discount, product_code=product.product_code, tax_rate=ipi_rate,
                )
            total += subtotal
            total_ipi += ipi_value

            localized_description = product.description
            if market_code == "EU":
                pt_pt, en = localized_descriptions.get(product.id, (None, None))
                localized_description = (en if payload.locale == "en-GB" else pt_pt) or product.description
            if item_in.is_special:
                localized_description = _special_description(localized_description)
            order_items.append(OrderItem(
                id=uuid.uuid4(),
                product_code=product.product_code,
                description=localized_description,
                is_circular=product.is_circular,
                altura=product.altura,
                largura=product.largura,
                profundidade=product.profundidade,
                opt_categories=item_in.opt_categories,
                optional_choices=optional_choices,
                qty=qty,
                sold_by_area=sold_by_area,
                area_width_m=width_m,
                area_depth_m=depth_m,
                area_pieces=area_pieces,
                unit_price=unit_price,
                discount=discount,
                ipi_rate=ipi_rate,
                ipi_value=ipi_value,
                tax_label=context.tax_label,
                currency=context.currency,
                observacao=product.observacao,
                comment=item_in.comment,
                is_special=item_in.is_special,
                special_code=special_code,
                special_percent=item_in.special_percent,
            ))
            if not lenient:
                strict_items.append(order_items[-1])
        except HTTPException as exc:
            if not lenient:
                raise
            skipped.append({"product_code": item_in.product_code, "reason": str(exc.detail)})

    if copy_source is not None and not order_items:
        raise HTTPException(
            status_code=422,
            detail="Nenhum item pôde ser copiado: "
            + "; ".join(f"{row['product_code']}: {row['reason']}" for row in skipped),
        )
    # Na cópia, o especial herdado da origem mantém o comentário que tinha; o que é
    # novo na tela segue a regra de sempre (especial sem comentário não é salvo).
    _ensure_special_comments(strict_items)
    catalog = await _order_catalog(
        db,
        [product_map[order_item.product_code] for order_item in order_items],
        catalog_scope,
    )
    total = _money(total)
    total_ipi = _money(total_ipi)
    total_with_ipi = _money(total + total_ipi)
    _ensure_total_capacity(total, total_ipi, total_with_ipi)
    code, orc_id, order_number = await _next_codes(db, current_user.id, market_code)
    order = Order(
        id=uuid.uuid4(),
        market_code=market_code,
        price_list_code=price_list.code,
        currency=context.currency,
        locale=(payload.locale if market_code == "EU" and payload.locale else context.locale),
        code=code,
        number_owner_id=current_user.id,
        order_number=order_number,
        orc_id=orc_id,
        client_id=payload.client_id,
        rep_id=payload.rep_id,
        catalog_id=catalog.id if catalog else None,
        catalog_name=catalog.name if catalog else None,
        total_value=total,
        total_ipi=total_ipi,
        total_with_ipi=total_with_ipi,
        vat_exempt=vat_exempt,
        vat_exemption_code=vat_exemption_code,
        notes=payload.notes,
        supersedes_order_id=source_order.id if source_order else None,
        revision_number=(source_order.revision_number + 1) if source_order else 1,
        items=order_items,
    )
    db.add(OrderHistory(
        id=uuid.uuid4(), order_id=order.id, user_id=current_user.id,
        action="created", items_snapshot=_items_history_snapshot(order_items),
        details="; ".join(filter(None, [
            f"copiado de {copy_source.code}" if copy_source is not None else None,
            f"IVA isento ({vat_exemption_code})" if vat_exempt else None,
        ])) or None,
    ))
    try:
        db.add(order)
        await touch_client_activity(db, client.id)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error(
            "Falha ao criar pedido: code=%s client_id=%s user_id=%s",
            code, payload.client_id, current_user.id, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Falha ao criar o pedido. Tente novamente.")
    order = await _reload_order_for_response(db, order.id)
    logger.info("Pedido criado: code=%s orc=%s total=%.2f user_id=%s", code, orc_id, order.total_value, current_user.id)
    return order, skipped


def _copy_item_payload(item: OrderItem) -> OrderItemCreate:
    """Item de origem → payload de criação. Só entram escolhas, medidas e
    comentário: preço, imposto e totais são recalculados pelo servidor."""
    return OrderItemCreate(
        product_code=item.product_code,
        qty=None if item.sold_by_area else item.qty,
        area_width_m=item.area_width_m if item.sold_by_area else None,
        area_depth_m=item.area_depth_m if item.sold_by_area else None,
        area_pieces=(item.area_pieces or 1) if item.sold_by_area else None,
        discount=item.discount or _ZERO,
        is_special=item.is_special,
        special_code=item.special_code,
        special_percent=item.special_percent,
        opt_categories=dict(item.opt_categories or {}),
        optional_choices=[
            OptionalChoiceCreate(
                application_id=choice.application_id,
                optional_id=choice.optional_id,
                custom_text=choice.custom_text,
            )
            for choice in item.optional_choices
            if choice.application_id is not None
        ],
        comment=item.comment,
    )


@router.post("/{order_id}/copy", response_model=OrderCopyRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def copy_order(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    body: OrderCopyRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Cria um orçamento novo (rascunho) com os itens escolhidos de um pedido.

    Diferente da revisão (`supersedes`): o pedido de origem não muda e o novo
    orçamento recalcula preço, desconto e imposto com as regras de hoje.
    """
    if not _can_create_order(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação não permitida para o seu nível de acesso.",
        )
    source = (await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.market_code == principal.code,
            *_order_visibility_filters(current_user),
        )
        .options(selectinload(Order.items).selectinload(OrderItem.optional_choices))
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    wanted = set(body.item_ids)
    selected = [item for item in source.items if item.id in wanted]
    if len(selected) != len(wanted):
        raise HTTPException(status_code=422, detail="Item não pertence ao pedido de origem.")

    skipped: list[dict] = []
    payload_items: list[OrderItemCreate] = []
    for item in selected:
        try:
            payload_items.append(_copy_item_payload(item))
        except ValueError:
            skipped.append({
                "product_code": item.product_code,
                "reason": "Item não pôde ser convertido para um novo orçamento.",
            })
    if not payload_items:
        raise HTTPException(
            status_code=422,
            detail="Nenhum item pôde ser copiado: "
            + "; ".join(f"{row['product_code']}: {row['reason']}" for row in skipped),
        )
    is_eu = principal.code == "EU"
    payload = OrderCreate(
        client_id=source.client_id,
        rep_id=source.rep_id,
        # Brasil usa sempre a tabela atual do cliente; EU mantém a escolhida.
        price_list_code=source.price_list_code if is_eu else None,
        locale=source.locale if is_eu and source.locale in ("pt-PT", "en-GB") else None,
        items=payload_items,
    )
    order, core_skipped = await _create_order_core(
        payload, db, current_user, principal, copy_source=source,
    )
    return {"order": order, "skipped": skipped + core_skipped}


@router.post("/{order_id}/revision", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order_revision(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if not _can_operate_order(current_user):
        raise HTTPException(status_code=403, detail="Somente operador pode criar revisão.")
    source = (await db.execute(select(Order).where(
        Order.id == order_id, Order.market_code == principal.code,
        *_order_visibility_filters(current_user),
    ))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if not (source.is_finalized and not source.is_cancelled):
        raise HTTPException(status_code=409, detail="Somente pedido finalizado pode receber revisão.")
    payload = OrderCreate(
        client_id=source.client_id, rep_id=source.rep_id, notes=source.notes,
        price_list_code=source.price_list_code,
        locale=source.locale if source.market_code == "EU" else None,
        supersedes_order_id=source.id,
        vat_exempt=source.vat_exempt,
        vat_exemption_code=source.vat_exemption_code,
        items=[OrderItemCreate(
            product_code=item.product_code, qty=item.qty,
            area_width_m=item.area_width_m, area_depth_m=item.area_depth_m,
            area_pieces=item.area_pieces if item.sold_by_area else None,
            discount=item.discount, opt_categories=item.opt_categories,
            source_order_item_id=item.id, comment=item.comment,
            is_special=item.is_special, special_code=item.special_code,
            special_percent=item.special_percent,
        ) for item in source.items],
    )
    # O fluxo normal recalcula preços e impostos atuais e cria novo número;
    # nenhuma assinatura ou preço antigo é copiado como se ainda fosse válido.
    return await create_order(payload, db, current_user, principal)


@router.get("", response_model=List[OrderListRead])
async def list_orders(
    response: Response,
    skip: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    q: str | None = Query(default=None, max_length=100),
    client_id: uuid.UUID | None = Query(default=None),
    rep_id: uuid.UUID | None = Query(default=None),
    client_name: str | None = Query(default=None, max_length=100),
    rep_name: str | None = Query(default=None, max_length=100),
    order_status: Literal["in_progress", "finalized", "cancelled", "not_finalized"] | None = Query(
        default=None,
        alias="status",
    ),
    order_stage: Literal["production", "delivered"] | None = Query(default=None, alias="stage"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    date_basis: Literal["created_at", "finalized_at"] = Query(default="created_at"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    conditions = []
    # A aba Pedido (finalizados) ordena e filtra pela data de finalização;
    # a aba Orçamento continua usando a data de criação.
    basis_column = Order.finalized_at if date_basis == "finalized_at" else Order.created_at
    if date_basis == "finalized_at":
        conditions.append(Order.is_finalized.is_(True))
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        conditions.append(Order.rep_id == current_user.rep_id)
    elif is_client_account(current_user):
        if not current_user.linked_id:
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        conditions.append(Order.client_id == current_user.linked_id)

    if client_id:
        conditions.append(Order.client_id == client_id)
    if rep_id:
        conditions.append(Order.rep_id == rep_id)
    if client_name and client_name.strip():
        conditions.append(
            Client.name.ilike(
                literal_contains_pattern(client_name.strip()),
                escape="\\",
            )
        )
    if rep_name and rep_name.strip():
        conditions.append(
            Representative.name.ilike(
                literal_contains_pattern(rep_name.strip()),
                escape="\\",
            )
        )
    if q and q.strip():
        pattern = literal_contains_pattern(q.strip())
        conditions.append(
            or_(
                Order.code.ilike(pattern, escape="\\"),
                Order.orc_id.ilike(pattern, escape="\\"),
                Client.name.ilike(pattern, escape="\\"),
                Representative.name.ilike(pattern, escape="\\"),
            )
        )
    if order_stage:
        conditions.append(Order.order_stage == order_stage)
    if order_status == "finalized":
        conditions.append(Order.is_finalized.is_(True))
    elif order_status == "cancelled":
        conditions.append(Order.is_cancelled.is_(True))
    elif order_status == "not_finalized":
        # Aba "Orçamento": em andamento + cancelados (só orçamento não finalizado
        # pode ser cancelado); o que foi finalizado vive na aba "Pedido".
        conditions.append(Order.is_finalized.is_(False))
    elif order_status == "in_progress":
        conditions.extend(
            (Order.is_finalized.is_(False), Order.is_cancelled.is_(False))
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Data inicial não pode ser posterior à data final.")
    if date_from:
        conditions.append(
            basis_column
            >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to:
        conditions.append(
            basis_column
            < datetime.combine(
                date_to + timedelta(days=1),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
        )

    stmt = (
        select(
            Order.id,
            Order.code,
            Order.orc_id,
            Order.market_code,
            Order.currency,
            Order.client_id,
            Client.name.label("client_name"),
            Order.rep_id,
            Representative.name.label("rep_name"),
            Order.catalog_id,
            Order.catalog_name,
            Order.total_value,
            Order.total_with_ipi,
            Order.is_finalized,
            Order.is_cancelled,
            Order.finalized_at,
            Order.cancelled_at,
            Order.order_stage,
            Order.production_started_at,
            Order.delivered_at,
            Order.created_at,
        )
        .select_from(Order)
        .join(Client, Client.id == Order.client_id)
        .outerjoin(Representative, Representative.id == Order.rep_id)
        .where(Order.market_code == principal.code, *conditions)
        .order_by(basis_column.desc(), Order.id.desc())
    )

    if cursor:
        cursor_created_at, cursor_id = _decode_order_cursor(cursor)
        stmt = stmt.where(
            tuple_(basis_column, Order.id) < tuple_(cursor_created_at, cursor_id)
        )
    elif skip:
        # Mantém compatibilidade com consumidores antigos; a interface nova usa cursor.
        stmt = stmt.offset(skip)

    rows = (await db.execute(stmt.limit(limit + 1))).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items_by_order: dict[uuid.UUID, list[dict]] = {
        row["id"]: [] for row in page_rows
    }
    if items_by_order:
        item_rows = (
            await db.execute(
                select(OrderItem.order_id, OrderItem.product_code, OrderItem.is_special, OrderItem.special_code, OrderItem.special_percent, OrderItem.qty)
                .where(OrderItem.order_id.in_(items_by_order))
                .order_by(OrderItem.order_id, OrderItem.created_at, OrderItem.id)
            )
        ).all()
        for order_id_value, product_code, is_special, special_code, special_percent, qty in item_rows:
            items_by_order[order_id_value].append(
                {"product_code": product_code, "is_special": is_special, "special_code": special_code,
                 "special_percent": special_percent, "qty": float(qty)}
            )

    if has_more and page_rows:
        last = page_rows[-1]
        response.headers["X-Next-Cursor"] = _encode_order_cursor(
            last["finalized_at"] if date_basis == "finalized_at" else last["created_at"],
            last["id"],
        )
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(page_rows))

    return [
        OrderListRead(
            **dict(row),
            items=items_by_order.get(row["id"], []),
        )
        for row in page_rows
    ]


@router.get("/history", response_model=List[OrderHistoryRead])
async def list_global_history(
    response: Response,
    skip: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=256),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if not (current_user.role == UserRole.admin or is_internal_operator(current_user)):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    stmt = select(OrderHistory).join(Order, Order.id == OrderHistory.order_id).where(
        Order.market_code == principal.code
    )
    if cursor:
        cursor_created_at, cursor_id = _decode_order_cursor(cursor)
        stmt = stmt.where(
            tuple_(OrderHistory.created_at, OrderHistory.id)
            < tuple_(cursor_created_at, cursor_id)
        )
    elif skip:
        stmt = stmt.offset(skip)

    result = await db.execute(
        stmt.order_by(
            OrderHistory.created_at.desc(),
            OrderHistory.id.desc(),
        ).limit(limit + 1)
    )
    rows = result.scalars().all()
    has_more = len(rows) > limit
    page = rows[:limit]
    if has_more and page:
        last = page[-1]
        response.headers["X-Next-Cursor"] = _encode_order_cursor(
            last.created_at,
            last.id,
        )
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(page))
    return page


@router.put("/{order_id}", response_model=OrderRead)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    # Edição é operação de admin, operador interno ou representante — cliente
    # final e conta de catálogo nunca editam pedido (SEC-02/Bloco de segurança 01).
    if not _can_operate_order(current_user):
        raise HTTPException(status_code=403, detail="Operação não permitida.")

    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.market_code == principal.code,
            *_order_visibility_filters(current_user),
        ).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já finalizado e não pode ser editado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado e não pode ser editado.")
    if (
        payload.price_list_code is not None
        and payload.price_list_code != order.price_list_code
        and payload.items is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Alterar a tabela de preço exige reenviar os itens para recalcular o orçamento.",
        )
    # Migration/01: toda edição aceita incrementa o frescor para consumidores
    # externos (leitura cross-database do Ilya Estoque).
    order.source_version += 1
    order.document_version += 1

    changes: list[str] = []

    vat_exempt, vat_exemption_code = _resolve_vat_exemption(
        current_user, order.market_code, payload.vat_exempt, payload.vat_exemption_code,
        (order.vat_exempt, order.vat_exemption_code),
    )
    if (vat_exempt, vat_exemption_code) != (order.vat_exempt, order.vat_exemption_code):
        if payload.items is None:
            raise HTTPException(
                status_code=422,
                detail="Alterar a isenção de IVA exige reenviar os itens para recalcular o orçamento.",
            )
        changes.append(
            f"IVA: isento ({vat_exemption_code})" if vat_exempt else "IVA: isenção removida"
        )
        order.vat_exempt = vat_exempt
        order.vat_exemption_code = vat_exemption_code

    if payload.notes is not None and payload.notes != order.notes:
        changes.append(f"observações alteradas")
        order.notes = payload.notes

    selected_rep: Representative | None = None
    if payload.rep_id is not None:
        if (
            current_user.role == UserRole.representante
            and payload.rep_id != current_user.rep_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Representante não pode transferir o pedido para outro representante.",
            )
        selected_rep = (
            await db.execute(
                select(Representative).where(
                    Representative.id == payload.rep_id,
                    Representative.market_code == principal.code,
                    Representative.relationship_ended_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not selected_rep:
            raise HTTPException(
                status_code=404,
                detail="Representante não encontrado.",
            )
        require_launch_country(principal.code, selected_rep.country)
        if payload.rep_id != order.rep_id:
            order.rep_id = payload.rep_id
            changes.append("representante alterado")
        if payload.items is None:
            # DEC-05: o novo representante precisa vender os catálogos do pedido.
            # Com itens, a mesma checagem acontece junto da validação deles.
            client = (await db.execute(select(Client).where(
                Client.id == order.client_id,
                Client.market_code == principal.code,
            ))).scalar_one()
            if current_user.role == UserRole.representante:
                ensure_price_visible(
                    await visible_price_scope(db, current_user, principal.code),
                    order.price_list_code,
                )
            _ensure_catalogs_allowed(
                order_catalog_scope(current_user, client, selected_rep),
                await _order_item_catalog_ids(db, order),
            )

    if payload.items is not None:
        _ensure_special_scope(current_user, principal.code, payload.items)
        old_item_map = {item.id: item for item in order.items}
        old_codes = {i.product_code for i in order.items}
        new_codes = {i.product_code for i in payload.items}
        removed = old_codes - new_codes
        added = new_codes - old_codes
        if removed:
            changes.append(f"removidos: {', '.join(removed)}")
        if added:
            changes.append(f"adicionados: {', '.join(added)}")
        old_comments = sorted(item.comment for item in order.items if item.comment)
        new_comments = sorted(item.comment for item in payload.items if item.comment)
        if old_comments != new_comments:
            changes.append("comentários dos itens alterados")

        # Valida e calcula TODOS os itens novos ANTES de deletar os antigos (V-B2).
        # Batch-fetch de produtos/tipos elimina N+1 (V-B1).
        product_map, type_map = await _load_products_and_types(
            db,
            [i.product_code for i in payload.items],
            principal.code,
            allow_inactive_codes=old_codes,
        )
        client = (await db.execute(select(Client).where(
            Client.id == order.client_id,
            Client.market_code == principal.code,
        ))).scalar_one_or_none()
        requested_price_list_code = (
            payload.price_list_code
            if order.market_code == "EU" and payload.price_list_code is not None
            else order.price_list_code
        )
        price_list = (await db.execute(select(PriceList).where(
            PriceList.market_code == order.market_code,
            PriceList.code == requested_price_list_code,
            PriceList.is_active.is_(True),
        ))).scalar_one_or_none()
        if not client or not price_list:
            raise HTTPException(status_code=422, detail="Escopo comercial do pedido não está mais disponível.")
        if order.market_code == "BR":
            _ensure_order_price_list_allowed(payload.price_list_code, client, order.price_list_code)
        require_launch_country(principal.code, client.country)
        if order.market_code == "BR":
            ensure_price_visible(
                await visible_price_scope(db, current_user, principal.code),
                price_list.code,
            )
        product_ids = [product.id for product in product_map.values()]
        available_ids = set((await db.execute(select(ProductMarket.product_id).where(
            ProductMarket.market_code == order.market_code,
            ProductMarket.is_available.is_(True),
            ProductMarket.product_id.in_(product_ids),
        ))).scalars().all())
        price_map = dict((await db.execute(select(ProductPrice.product_id, ProductPrice.amount).where(
            ProductPrice.price_list_id == price_list.id,
            ProductPrice.product_id.in_(product_ids),
        ))).all())
        product_market_rows = (await db.execute(select(
            ProductMarket.product_id,
            ProductMarket.vat_rate,
            ProductMarket.vat_status,
            ProductMarket.description_pt_pt,
            ProductMarket.description_en,
        ).where(
            ProductMarket.market_code == order.market_code,
            ProductMarket.product_id.in_(product_ids),
        ))).all()
        product_vat = {
            row.product_id: (row.vat_rate, row.vat_status) for row in product_market_rows
        }
        group_vat = await _load_eu_group_vat_rates(db, type_map) if order.market_code == "EU" else {}
        localized_descriptions = {
            row.product_id: (row.description_pt_pt, row.description_en)
            for row in product_market_rows
        }
        rep = selected_rep
        if rep is None and order.rep_id:
            rep = (
                await db.execute(
                    select(Representative).where(
                        Representative.id == order.rep_id,
                        Representative.market_code == principal.code,
                        Representative.relationship_ended_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if rep:
            require_launch_country(principal.code, rep.country)
        max_discount = _resolve_max_discount(
            current_user, client, rep, order.market_code, price_list.code
        )

        total = _ZERO
        total_ipi = _ZERO
        new_items: list[OrderItem] = []
        used_source_ids: set[uuid.UUID] = set()
        used_special_codes: set[str] = set()
        for item_in in payload.items:
            product = product_map.get(item_in.product_code)
            if not product:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
            if product.id not in available_ids and product.product_code not in old_codes:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não está disponível neste mercado.")
            if product.id not in price_map:
                raise HTTPException(status_code=422, detail=f"Produto '{item_in.product_code}' não possui preço na lista {price_list.name}.")
            if item_in.source_order_item_id and item_in.source_order_item_id not in old_item_map:
                raise HTTPException(status_code=422, detail="Item não pertence ao pedido editado.")
            optional_choices = await _resolve_item_choices(
                db, product, principal.code, item_in,
                old_item_map.get(item_in.source_order_item_id),
                require_complete=principal.code != "EU",
            )
            product_type = type_map.get(product.type)
            if order.market_code == "EU":
                vat_rate, vat_status = product_vat.get(product.id, (None, None))
                ipi_rate = _resolve_eu_vat(
                    product.product_code, vat_rate, vat_status,
                    group_vat.get(product_type.group_id) if product_type else None,
                )
            else:
                ipi_rate = _resolve_br_ipi(product.product_code, product_type)
            if vat_exempt:
                ipi_rate = _ZERO
            qty, sold_by_area, width_m, depth_m, area_pieces = _resolve_item_measurement(
                product, item_in, old_item_map.get(item_in.source_order_item_id)
            )
            line_max_discount = max_discount
            if order.market_code == "EU" and item_in.source_order_item_id is not None:
                if item_in.source_order_item_id not in used_source_ids:
                    used_source_ids.add(item_in.source_order_item_id)
                    old_item = old_item_map.get(item_in.source_order_item_id)
                    if old_item is not None:
                        line_max_discount = _edit_line_max_discount(
                            max_discount,
                            old_item,
                            product.product_code,
                            price_list.code == order.price_list_code,
                        )
            special_code = None
            if item_in.is_special:
                special_code = _resolve_special_code(item_in, product.product_code, used_special_codes)
                unit_price, discount, subtotal, ipi_rate, ipi_value = _calculate_special_order_line(
                    base_price=price_map[product.id], qty=qty,
                    special_percent=item_in.special_percent, tax_rate=ipi_rate,
                    product_code=product.product_code,
                )
            else:
                unit_price, discount, subtotal, ipi_rate, ipi_value = _calculate_order_line(
                    unit_price=price_map[product.id], qty=qty,
                    discount=item_in.discount or _ZERO, max_discount=line_max_discount,
                    product_code=product.product_code, tax_rate=ipi_rate,
                )
            total += subtotal
            total_ipi += ipi_value

            localized_description = product.description
            if order.market_code == "EU":
                pt_pt, en = localized_descriptions.get(product.id, (None, None))
                localized_description = (en if order.locale == "en-GB" else pt_pt) or product.description
            if item_in.is_special:
                localized_description = _special_description(localized_description)
            new_items.append(OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                product_code=product.product_code,
                description=localized_description,
                is_circular=product.is_circular,
                altura=product.altura,
                largura=product.largura,
                profundidade=product.profundidade,
                opt_categories=item_in.opt_categories,
                optional_choices=optional_choices,
                qty=qty,
                sold_by_area=sold_by_area,
                area_width_m=width_m,
                area_depth_m=depth_m,
                area_pieces=area_pieces,
                unit_price=unit_price,
                discount=discount,
                ipi_rate=ipi_rate,
                ipi_value=ipi_value,
                tax_label="IVA" if order.market_code == "EU" else "IPI",
                currency=order.currency,
                observacao=product.observacao,
                comment=item_in.comment,
                is_special=item_in.is_special,
                special_code=special_code,
                special_percent=item_in.special_percent,
            ))

        _ensure_special_comments(new_items)
        catalog = await _order_catalog(
            db,
            [product_map[item_in.product_code] for item_in in payload.items],
            order_catalog_scope(current_user, client, rep),
        )
        new_catalog_id = catalog.id if catalog else None
        if new_catalog_id != order.catalog_id:
            changes.append("catálogo alterado")
        order.catalog_id = new_catalog_id
        order.catalog_name = catalog.name if catalog else None
        if price_list.code != order.price_list_code:
            changes.append(f"tabela de preço: {order.price_list_code} → {price_list.code}")
            order.price_list_code = price_list.code

        # Tudo validado: agora sim remove os antigos e insere os novos.
        for item in order.items:
            await db.delete(item)
        await db.flush()

        total = _money(total)
        total_ipi = _money(total_ipi)
        total_with_ipi = _money(total + total_ipi)
        _ensure_total_capacity(total, total_ipi, total_with_ipi)
        old_total = _decimal(order.total_value)
        order.total_value = total
        order.total_ipi = total_ipi
        order.total_with_ipi = total_with_ipi
        if abs(old_total - total) > _CENT:
            changes.append(f"total: {order.currency} {old_total:.2f} → {order.currency} {total:.2f}")
        for item in new_items:
            db.add(item)

    detail = "; ".join(changes) if changes else "sem alterações"
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="edited",
        details=detail,
        items_snapshot=_items_history_snapshot(new_items if payload.items is not None else order.items),
    ))
    await touch_client_activity(db, order.client_id)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("Falha ao editar pedido: id=%s user=%s", order_id, current_user.id, exc_info=True)
        raise HTTPException(status_code=500, detail="Falha ao salvar as alterações do pedido. Tente novamente.")
    order = await _reload_order_for_response(db, order.id)
    logger.info("Pedido editado: id=%s user=%s changes=%s", order_id, current_user.id, detail)
    return order


class FinalizePayload(BaseModel):
    external_code: str | None = Field(None, max_length=100)


@router.post("/{order_id}/finalize", response_model=OrderRead)
async def finalize_order(
    order_id: uuid.UUID,
    payload: FinalizePayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if not _can_operate_order(current_user):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            *_order_visibility_filters(current_user),
        )
        .options(
            selectinload(Order.items).selectinload(
                OrderItem.optional_choices
            )
        )
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já está finalizado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser finalizado.")
    _ensure_special_comments(order.items, finalizing=True)
    pending = await _pending_optionals_by_item(db, order)
    pending_items = [
        f"{item.product_code}: {', '.join(pending[item.id])}"
        for item in order.items
        if item.id in pending
    ]
    if pending_items:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selecione todos os opcionais antes de finalizar. "
                "Pendências: " + "; ".join(pending_items)
            ),
        )
    terminal_at = datetime.now(timezone.utc)
    order.is_finalized = True
    order.finalized_at = terminal_at
    order.order_stage = "production"
    order.production_started_at = terminal_at
    order.source_version += 1
    order.document_version += 1
    if payload.external_code:
        order.external_code = payload.external_code
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="finalized",
        details=f"código externo: {payload.external_code}" if payload.external_code else None,
    ))
    await touch_client_activity(db, order.client_id, terminal_at)
    if order.market_code == "EU":
        await enqueue_finalized_eu_order(db, order.id)
    if settings.ORDER_EMAIL_MODE != "off":
        try:
            # O pedido tem prioridade: o savepoint impede que uma falha da fila
            # de e-mail deixe lixo ou desfaça a finalização.
            async with db.begin_nested():
                await enqueue_order_emails(
                    db,
                    order,
                    requested_by_user_id=current_user.id,
                )
        except Exception:
            logger.exception(
                "Falha ao enfileirar e-mail do pedido: order_id=%s",
                order.id,
            )
    await db.commit()
    order = await _reload_order_for_response(db, order.id)
    logger.info("Pedido finalizado: id=%s ext=%s user=%s", order_id, payload.external_code, current_user.id)
    return order


@router.post("/{order_id}/stage", response_model=OrderRead)
@limiter.limit("30/minute")
async def change_order_stage(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    payload: OrderStageUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if not _can_operate_order(current_user):
        raise HTTPException(403, "Acesso negado.")
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.market_code == principal.code,
            *_order_visibility_filters(current_user),
        ).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_cancelled or not order.is_finalized:
        raise HTTPException(status_code=409, detail="Somente pedido finalizado pode mudar de etapa.")
    etapa_anterior = order.order_stage or "production"
    if payload.stage == etapa_anterior and order.order_stage is not None:
        return await _reload_order_for_response(db, order.id)
    now = datetime.now(timezone.utc)
    if payload.stage == "delivered":
        order.order_stage = "delivered"
        order.delivered_at = now
        if order.production_started_at is None:
            order.production_started_at = order.finalized_at
    else:
        order.order_stage = "production"
        order.delivered_at = None
        if order.production_started_at is None:
            order.production_started_at = order.finalized_at
    order.source_version += 1
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="stage_changed",
        details=f"{etapa_anterior} -> {payload.stage}",
    ))
    await db.commit()
    order = await _reload_order_for_response(db, order.id)
    logger.info(
        "Etapa do pedido alterada: id=%s de=%s para=%s user=%s",
        order_id,
        etapa_anterior,
        payload.stage,
        current_user.id,
    )
    return order


class CancelPayload(BaseModel):
    reason: str | None = Field(None, max_length=1000)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: uuid.UUID,
    payload: CancelPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if not _can_operate_order(current_user):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            *_order_visibility_filters(current_user),
        ).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido finalizado não pode ser cancelado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido já está cancelado.")
    terminal_at = datetime.now(timezone.utc)
    order.is_cancelled = True
    order.cancelled_at = terminal_at
    order.source_version += 1
    order.document_version += 1
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="cancelled",
        details=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
    ))
    await touch_client_activity(db, order.client_id, terminal_at)
    await db.commit()
    order = await _reload_order_for_response(db, order.id)
    logger.info("Pedido cancelado: id=%s user=%s", order_id, current_user.id)
    return order


@router.get("/{order_id}/history", response_model=List[OrderHistoryRead])
async def get_order_history(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
):
    result = await db.execute(select(Order).where(
        Order.id == order_id,
        *_order_visibility_filters(current_user),
    ))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    hist = await db.execute(
        select(OrderHistory).where(OrderHistory.order_id == order_id).order_by(OrderHistory.created_at.asc())
    )
    return hist.scalars().all()


@router.get("/{id_or_code}", response_model=OrderRead)
async def get_order(
    id_or_code: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
):
    order = await _get_order(db, id_or_code, current_user)
    return await _annotate_pending_optionals(db, order)


async def _order_delete_blocker(db: AsyncSession, order: Order) -> str | None:
    """Motivo pelo qual o pedido não pode ser excluído, ou None se pode.

    As FKs de revisão e e-mail são RESTRICT de propósito: guardam evidência de
    envio. Em vez de deixar o banco estourar um 409 genérico, dizemos qual
    registro bloqueia. Cancelar não é saída: o endpoint /cancel recusa pedido
    finalizado, e esses registros só existem nele. O job do Moloni NÃO bloqueia:
    `delete_order` o apaga junto, registrando o documento no log.
    """
    async def has(model, column) -> bool:
        stmt = select(model.id).where(column == order.id).limit(1)
        return (await db.execute(stmt)).first() is not None

    if await has(Order, Order.supersedes_order_id):
        return "Este pedido tem uma revisão. Exclua a revisão primeiro."
    if await has(OrderEmailDocument, OrderEmailDocument.order_id) or await has(
        OrderEmailDelivery, OrderEmailDelivery.order_id
    ):
        return "Pedido já teve envio de e-mail registrado e não pode ser excluído."
    return None


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Exclusão física, exclusiva do admin (decisão do Alto Comando, 13/08).

    Reabre o que o commit 241d219 havia bloqueado em nome da retenção. A
    contrapartida é sinalizar a saída: um consumidor que mantém projeção por
    ID do Ilya (serviço Estoque) não detecta um DELETE — a linha some sem
    bump de `source_version` e a cópia de lá ficaria órfã para sempre. Por
    isso o evento `order.deleted` vai para a outbox na MESMA transação: ou os
    dois acontecem, ou nenhum. Cancelar (`/cancel`) continua sendo o caminho
    recomendado para pedido com histórico comercial.
    """
    result = await db.execute(select(Order).where(
        Order.id == order_id, Order.market_code == principal.code,
    ).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    blocker = await _order_delete_blocker(db, order)
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)

    await enqueue_event(
        db,
        "order.deleted",
        {
            "order_id": str(order.id),
            "code": order.code,
            "orc_id": order.orc_id,
            "client_id": str(order.client_id),
            "was_finalized": order.is_finalized,
            "deleted_by": str(current_user.id),
        },
    )
    # A FK moloni_export_jobs.order_id é RESTRICT: apagamos o(s) job(s) aqui,
    # explicitamente e na mesma transação da exclusão. Documento já emitido no
    # Moloni não é desfeito; o log guarda o número para conferência fiscal e
    # eventual nota de crédito. Job `processing` também vai: o worker está
    # bloqueado (MOLONI_BLOCKED) e, se voltar, não acha mais o job.
    moloni_jobs = (await db.execute(
        select(MoloniExportJob).where(MoloniExportJob.order_id == order.id)
    )).scalars().all()
    for job in moloni_jobs:
        if job.moloni_document_id is not None or job.status in ("delivered", "processing"):
            logger.warning(
                "Pedido excluído com registro Moloni: code=%s job_id=%s status=%s moloni_document_id=%s",
                order.code,
                job.id,
                job.status,
                job.moloni_document_id,
            )
        await db.delete(job)
    if moloni_jobs:
        await db.flush()
    try:
        await db.delete(order)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Pedido com revisão ou evidência não pode ser excluído.")
    logger.warning(
        "Pedido excluído: id=%s code=%s por user_id=%s",
        order_id,
        order.code,
        current_user.id,
    )


