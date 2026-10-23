import base64
import binascii
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from app.core.lifecycle import touch_client_activity
from app.models.catalog import Catalog
from app.core.search import literal_contains_pattern
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.services.moloni_jobs import enqueue_finalized_eu_order
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
from app.schemas.order import OrderCreate, OrderItemCreate, OrderRead, OrderListRead, OrderUpdate, OrderHistoryRead
from app.services.integration_events import enqueue_event

logger = logging.getLogger("ilya.orders")
router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")
_MAX_ORDER_TOTAL = Decimal("999999999999999999.99")


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


def _choice_snapshot(item: OrderItem) -> list[dict]:
    return [
        {
            "application_name": choice.application_name,
            "application_name_en": choice.application_name_en,
            "category_code": choice.category_code,
            "category_name": choice.category_name,
            "optional_name": choice.optional_name,
            "component_name": choice.component_name,
            "display_order": choice.display_order,
        }
        for choice in sorted(getattr(item, "optional_choices", []), key=lambda row: (row.display_order, str(row.id)))
    ]


def _items_history_snapshot(items: list[OrderItem]) -> list[dict]:
    return [
        {"product_code": item.product_code, "legacy_optionals": item.opt_categories,
         "applications": _choice_snapshot(item)} for item in items
    ]


async def _resolve_item_choices(
    db: AsyncSession, product: Product, market_code: str, item_in: OrderItemCreate,
    source: OrderItem | None = None,
) -> list[OrderItemOptionalChoice]:
    # An unchanged historical line is copied as a snapshot, even if the master
    # application or optional was removed after the original order.
    if source is not None and source.product_code == item_in.product_code and source.opt_categories == item_in.opt_categories:
        old_pairs = {(row.application_id, row.optional_id) for row in source.optional_choices}
        new_pairs = {(row.application_id, row.optional_id) for row in item_in.optional_choices}
        if item_in.preserve_optional_choices or "optional_choices" not in item_in.model_fields_set or new_pairs == old_pairs:
            return [OrderItemOptionalChoice(
                id=uuid.uuid4(), application_id=row.application_id,
                optional_id=row.optional_id, application_name=row.application_name,
                application_name_en=row.application_name_en,
                category_code=row.category_code, category_name=row.category_name,
                optional_name=row.optional_name, component_name=row.component_name,
                display_order=row.display_order,
            ) for row in source.optional_choices]

    applications = (await db.execute(select(ProductOptionalApplication).where(
        ProductOptionalApplication.product_id == product.id,
    ))).scalars().all()
    application_map = {row.id: row for row in applications}
    category_codes = {row.category.code for row in applications}
    if category_codes.intersection(item_in.opt_categories):
        raise HTTPException(status_code=422, detail="Categoria convertida deve usar aplicações, não o seletor antigo.")
    chosen = {row.application_id: row.optional_id for row in item_in.optional_choices}
    if len(chosen) != len(item_in.optional_choices) or any(app_id not in application_map for app_id in chosen):
        raise HTTPException(status_code=422, detail="Aplicação inválida ou repetida neste produto.")
    missing = [row.name for row in applications if row.required and row.id not in chosen]
    if missing:
        raise HTTPException(status_code=422, detail="Preencha as aplicações obrigatórias: " + ", ".join(missing))
    option_ids = set(chosen.values())
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
    for app_id, optional_id in chosen.items():
        app = application_map[app_id]
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
            component_name=component_map[app.component_id].description if app.component_id else None,
            display_order=app.display_order,
        ))
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
                Product.description,
                Product.type,
                Product.is_circular,
                Product.altura,
                Product.largura,
                Product.profundidade,
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


async def _order_catalog(
    db: AsyncSession,
    products: list[Product],
    scope: CatalogScope,
    *,
    current_catalog_id: uuid.UUID | None = None,
) -> Catalog:
    """Catálogo único do pedido, validado contra as permissões (MELH-07).

    Mistura de catálogos e troca do catálogo na edição/revisão são 422 (dado
    inválido); catálogo fora da permissão do cliente/representante é 403.
    """
    catalog_ids = {product.catalog_id for product in products}
    if len(catalog_ids) != 1:
        raise HTTPException(
            status_code=422,
            detail="Um pedido não pode misturar catálogos. Gere um pedido por catálogo.",
        )
    catalog_id = catalog_ids.pop()
    if current_catalog_id is not None and catalog_id != current_catalog_id:
        raise HTTPException(
            status_code=422,
            detail="A edição não pode trocar o catálogo do pedido.",
        )
    if not allows(scope, catalog_id):
        raise HTTPException(
            status_code=403,
            detail="Catálogo não liberado para este cliente ou representante.",
        )
    return (await db.execute(select(Catalog).where(Catalog.id == catalog_id))).scalar_one()


def _price_for_profile(product: Product, profile: str) -> Decimal:
    """Preço faturado conforme o perfil do cliente (V-Bloco62)."""
    if profile == "corporativo":
        return _money(product.price_corporativo)
    return _money(product.price_lojista)


def _resolve_max_discount(
    current_user: User,
    client: Client,
    rep: Representative | None,
) -> Decimal:
    """Bloco 69: teto dinamico por Cliente/Representante em vez de limite fixo por role."""
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
        detail=f"Produto '{product_code}' não possui IVA definido no produto ou no grupo europeu.",
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
            detail=f"Desconto de {discount_value}% no item '{product_code}' excede o limite permitido ({max_discount_value}%) para o seu nível de acesso.",
        )


def _calculate_order_line(
    *,
    unit_price: Decimal | float,
    qty: int,
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


async def _reload_order_for_response(db, order_id) -> Order:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.optional_choices))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
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

    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O usuário representante não possui um registro de representante associado."
            )
        payload.rep_id = current_user.rep_id

    if is_client_account(current_user) and payload.client_id != current_user.linked_id:
        # Cliente logado (V-Bloco66-RBAC): só pode criar pedido para si mesmo.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação não permitida para este cliente.")

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

    max_discount = _resolve_max_discount(current_user, client, rep)

    # Batch-fetch de produtos e tipos — elimina N+1 (V-B1)
    product_map, type_map = await _load_products_and_types(
        db, [i.product_code for i in payload.items], principal.code
    )
    market_code = principal.code
    context = principal.market
    price_list = (await db.execute(
        select(PriceList).where(
            PriceList.id == client.price_list_id,
            PriceList.market_code == market_code,
            PriceList.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not price_list:
        raise HTTPException(status_code=422, detail="Cliente sem lista de preços válida para o mercado ativo.")
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
    for item_in in payload.items:
        product = product_map.get(item_in.product_code)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
        if product.id not in available_ids:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não está disponível neste mercado.")
        if product.id not in price_map:
            raise HTTPException(status_code=422, detail=f"Produto '{item_in.product_code}' não possui preço na lista {price_list.name}.")
        if item_in.source_order_item_id and item_in.source_order_item_id not in source_items:
            raise HTTPException(status_code=422, detail="Item de origem inválido para esta revisão.")
        optional_choices = await _resolve_item_choices(
            db, product, market_code, item_in,
            source_items.get(item_in.source_order_item_id),
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
        unit_price, discount, subtotal, ipi_rate, ipi_value = (
            _calculate_order_line(
                unit_price=price_map[product.id],
                qty=item_in.qty,
                discount=item_in.discount or _ZERO,
                max_discount=max_discount,
                product_code=product.product_code,
                tax_rate=ipi_rate,
            )
        )
        total += subtotal
        total_ipi += ipi_value

        localized_description = product.description
        if market_code == "EU":
            pt_pt, en = localized_descriptions.get(product.id, (None, None))
            localized_description = (en if payload.locale == "en-GB" else pt_pt) or product.description
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
            qty=item_in.qty,
            unit_price=unit_price,
            discount=discount,
            ipi_rate=ipi_rate,
            ipi_value=ipi_value,
            tax_label=context.tax_label,
            currency=context.currency,
            observacao=product.observacao,
        ))

    catalog = await _order_catalog(
        db,
        [product_map[item_in.product_code] for item_in in payload.items],
        order_catalog_scope(current_user, client, rep),
        current_catalog_id=source_order.catalog_id if source_order else None,
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
        catalog_id=catalog.id,
        catalog_name=catalog.name,
        total_value=total,
        total_ipi=total_ipi,
        total_with_ipi=total_with_ipi,
        notes=payload.notes,
        supersedes_order_id=source_order.id if source_order else None,
        revision_number=(source_order.revision_number + 1) if source_order else 1,
        items=order_items,
    )
    db.add(OrderHistory(
        id=uuid.uuid4(), order_id=order.id, user_id=current_user.id,
        action="created", items_snapshot=_items_history_snapshot(order_items),
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
    return order


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
        locale=source.locale if source.market_code == "EU" else None,
        supersedes_order_id=source.id,
        items=[OrderItemCreate(
            product_code=item.product_code, qty=item.qty,
            discount=item.discount, opt_categories=item.opt_categories,
            source_order_item_id=item.id,
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
    order_status: Literal["in_progress", "finalized", "cancelled"] | None = Query(
        default=None,
        alias="status",
    ),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_order_access),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    conditions = []
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
    if order_status == "finalized":
        conditions.append(Order.is_finalized.is_(True))
    elif order_status == "cancelled":
        conditions.append(Order.is_cancelled.is_(True))
    elif order_status == "in_progress":
        conditions.extend(
            (Order.is_finalized.is_(False), Order.is_cancelled.is_(False))
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Data inicial não pode ser posterior à data final.")
    if date_from:
        conditions.append(
            Order.created_at
            >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to:
        conditions.append(
            Order.created_at
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
            Order.created_at,
        )
        .select_from(Order)
        .join(Client, Client.id == Order.client_id)
        .outerjoin(Representative, Representative.id == Order.rep_id)
        .where(Order.market_code == principal.code, *conditions)
        .order_by(Order.created_at.desc(), Order.id.desc())
    )

    if cursor:
        cursor_created_at, cursor_id = _decode_order_cursor(cursor)
        stmt = stmt.where(
            tuple_(Order.created_at, Order.id) < tuple_(cursor_created_at, cursor_id)
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
                select(OrderItem.order_id, OrderItem.product_code, OrderItem.qty)
                .where(OrderItem.order_id.in_(items_by_order))
                .order_by(OrderItem.order_id, OrderItem.created_at, OrderItem.id)
            )
        ).all()
        for order_id_value, product_code, qty in item_rows:
            items_by_order[order_id_value].append(
                {"product_code": product_code, "qty": qty}
            )

    if has_more and page_rows:
        last = page_rows[-1]
        response.headers["X-Next-Cursor"] = _encode_order_cursor(
            last["created_at"],
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
    # Migration/01: toda edição aceita incrementa o frescor para consumidores
    # externos (leitura cross-database do Ilya Estoque).
    order.source_version += 1
    order.document_version += 1

    changes: list[str] = []

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
            # DEC-05: o novo representante precisa vender o catálogo do pedido.
            # Com itens, a mesma checagem acontece junto da validação deles.
            client = (await db.execute(select(Client).where(
                Client.id == order.client_id,
                Client.market_code == principal.code,
            ))).scalar_one()
            if not allows(order_catalog_scope(current_user, client, selected_rep), order.catalog_id):
                raise HTTPException(
                    status_code=403,
                    detail="Catálogo não liberado para este cliente ou representante.",
                )

    if payload.items is not None:
        old_item_map = {item.id: item for item in order.items}
        old_codes = {i.product_code for i in order.items}
        new_codes = {i.product_code for i in payload.items}
        removed = old_codes - new_codes
        added = new_codes - old_codes
        if removed:
            changes.append(f"removidos: {', '.join(removed)}")
        if added:
            changes.append(f"adicionados: {', '.join(added)}")

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
        price_list = (await db.execute(select(PriceList).where(
            PriceList.market_code == order.market_code,
            PriceList.code == order.price_list_code,
            PriceList.is_active.is_(True),
        ))).scalar_one_or_none()
        if not client or not price_list:
            raise HTTPException(status_code=422, detail="Escopo comercial do pedido não está mais disponível.")
        require_launch_country(principal.code, client.country)
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
        max_discount = _resolve_max_discount(current_user, client, rep)

        total = _ZERO
        total_ipi = _ZERO
        new_items: list[OrderItem] = []
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
            unit_price, discount, subtotal, ipi_rate, ipi_value = (
                _calculate_order_line(
                    unit_price=price_map[product.id],
                    qty=item_in.qty,
                    discount=item_in.discount or _ZERO,
                    max_discount=max_discount,
                    product_code=product.product_code,
                    tax_rate=ipi_rate,
                )
            )
            total += subtotal
            total_ipi += ipi_value

            localized_description = product.description
            if order.market_code == "EU":
                pt_pt, en = localized_descriptions.get(product.id, (None, None))
                localized_description = (en if order.locale == "en-GB" else pt_pt) or product.description
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
                qty=item_in.qty,
                unit_price=unit_price,
                discount=discount,
                ipi_rate=ipi_rate,
                ipi_value=ipi_value,
                tax_label="IVA" if order.market_code == "EU" else "IPI",
                currency=order.currency,
                observacao=product.observacao,
            ))

        await _order_catalog(
            db,
            [product_map[item_in.product_code] for item_in in payload.items],
            order_catalog_scope(current_user, client, rep),
            current_catalog_id=order.catalog_id,
        )

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
        select(Order).where(
            Order.id == order_id,
            *_order_visibility_filters(current_user),
        ).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já está finalizado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser finalizado.")
    terminal_at = datetime.now(timezone.utc)
    order.is_finalized = True
    order.finalized_at = terminal_at
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
    await db.commit()
    order = await _reload_order_for_response(db, order.id)
    logger.info("Pedido finalizado: id=%s ext=%s user=%s", order_id, payload.external_code, current_user.id)
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
    return await _get_order(db, id_or_code, current_user)


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


