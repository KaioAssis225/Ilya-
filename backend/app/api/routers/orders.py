import base64
import binascii
import logging
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import false, or_, select, text, tuple_, update
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
from app.core.config import settings
from app.core.limiter import limiter
from app.core.lifecycle import touch_client_activity
from app.core.client_invites import invitation_delivery_ready, send_signature_invitation
from app.core.search import literal_contains_pattern
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.user import User, UserRole
from app.models.notification import Notification
from app.models.signature_invitation import SignatureInvitation
from app.models.order_signature_evidence import OrderSignatureEvidence
from app.models.market import ProductMarket, ProductPrice, PriceList, UserMarket, VAT_APPROVED
from app.core.markets import MarketPrincipal, require_launch_country
from app.schemas.order import OrderCreate, OrderItemCreate, OrderRead, OrderListRead, OrderUpdate, OrderHistoryRead
from app.services.integration_events import enqueue_event
from app.core.security import (
    generate_sign_invitation_token,
    hash_sign_invitation_token,
    sign_invitation_expiry,
)

logger = logging.getLogger("ilya.orders")
router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_CENT = Decimal("0.01")
_MAX_ORDER_TOTAL = Decimal("999999999999999999.99")


def _require_electronic_signatures_enabled() -> None:
    if not settings.ELECTRONIC_SIGNATURES_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Assinatura eletrônica temporariamente indisponível. "
                "Utilize os campos de assinatura manual do PDF."
            ),
        )


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

    Operador interno de vendas, representante e admin. Conta de catálogo
    (`produtos`) mantém leitura, mas não altera o ciclo comercial. Conta de
    portal do cliente-final nunca opera pedido (SEC-02) — `is_internal_operator`
    já exclui o legado `vendedor`+`linked_id`. Exclusão segue exclusiva do admin.
    """
    return (
        current_user.role
        in {UserRole.admin, UserRole.representante}
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


def _order_document_content(order: Order) -> dict:
    return {
        "order_id": str(order.id),
        "document_version": order.document_version or 1,
        "market_code": order.market_code,
        "code": order.code,
        "orc_id": order.orc_id,
        "client_id": str(order.client_id),
        "rep_id": str(order.rep_id) if order.rep_id else None,
        "price_list_code": order.price_list_code,
        "currency": order.currency,
        "locale": order.locale,
        "is_finalized": order.is_finalized,
        "is_cancelled": order.is_cancelled,
        "external_code": order.external_code,
        "total_value": str(order.total_value),
        "total_ipi": str(order.total_ipi),
        "total_with_ipi": str(order.total_with_ipi),
        "notes": order.notes,
        "items": [
            {
                "product_code": item.product_code,
                "description": item.description,
                "is_circular": item.is_circular,
                "altura": str(item.altura),
                "largura": str(item.largura),
                "profundidade": str(item.profundidade),
                "qty": item.qty,
                "unit_price": str(item.unit_price),
                "discount": str(item.discount),
                "ipi_rate": str(item.ipi_rate),
                "ipi_value": str(item.ipi_value),
                "tax_label": item.tax_label,
                "currency": item.currency,
                "observacao": item.observacao,
                "optionals": item.opt_categories,
            }
            for item in sorted(order.items, key=lambda current: str(current.id))
        ],
    }


def _order_document_hash(order: Order) -> str:
    canonical = json.dumps(_order_document_content(order), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _record_signature(
    db: AsyncSession, order: Order, *, signer_kind: str, signature: str,
    method: str, submitted_by_user_id: uuid.UUID | None = None,
    invitation_id: uuid.UUID | None = None,
) -> None:
    db.add(OrderSignatureEvidence(
        id=uuid.uuid4(), order_id=order.id, signer_kind=signer_kind,
        document_version=order.document_version or 1,
        document_hash=_order_document_hash(order),
        signature_hash=hashlib.sha256(signature.encode("utf-8")).hexdigest(),
        signed_at=datetime.now(timezone.utc), method=method,
        submitted_by_user_id=submitted_by_user_id,
        invitation_id=invitation_id, verification_status="captured",
    ))


def _invitation_is_valid(invitation: SignatureInvitation | None) -> bool:
    if not invitation or invitation.consumed_at or invitation.revoked_at or not invitation.sent_at:
        return False
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at >= datetime.now(timezone.utc)


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
    db: AsyncSession, codes: list[str], market_code: str
) -> tuple[dict[str, Product], dict[str, ProductType]]:
    """Carrega produtos e seus tipos em 2 queries (evita N+1 por item — V-B1)."""
    products = (await db.execute(
        select(Product)
        .where(
            Product.market_code == market_code,
            Product.product_code.in_(codes),
        )
        .options(
            load_only(
                Product.id,
                Product.product_code,
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
    # cliente-final e operador interno de vendas respeitam o teto do cliente
    if is_client_account(current_user) or current_user.role == UserRole.vendedor:
        return _decimal(client.max_discount)
    if current_user.role == UserRole.admin:
        return _HUNDRED
    # Papéis sem autorização comercial recebem zero por padrão. Isso evita que
    # uma nova role herde desconto integral ao cair neste fallback.
    return _ZERO


def _resolve_eu_vat(
    product_code: str,
    vat_rate: Decimal | None,
    vat_status: str | None,
) -> Decimal:
    """IVA faturável de Portugal: só taxa aprovada por uma pessoa conta.

    Sem herança do IPI do grupo e sem fallback para zero — se o SKU não tem
    `vat_status == approved` com uma taxa definida, o pedido é recusado. Como o
    aprovação nominal é gravada por produto e continua sendo verificada em toda
    criação ou recálculo de pedido, mesmo depois de o mercado EU ser ativado.
    """
    if vat_status != VAT_APPROVED or vat_rate is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Produto '{product_code}' não possui IVA aprovado para o mercado europeu.",
        )
    return _decimal(vat_rate)


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
            raise HTTPException(status_code=403, detail="Somente operador pode criar revisão de pedido assinado.")
        source_order = (await db.execute(select(Order).where(
            Order.id == payload.supersedes_order_id,
            Order.market_code == principal.code,
            *_order_visibility_filters(current_user),
        ).with_for_update())).scalar_one_or_none()
        if source_order is None or source_order.client_id != payload.client_id:
            raise HTTPException(status_code=404, detail="Pedido de origem não encontrado neste mercado e cliente.")
        if source_order.rep_signature is None and source_order.client_signature is None:
            raise HTTPException(status_code=409, detail="Revisão exige pedido de origem assinado.")
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
    localized_descriptions = {
        row.product_id: (row.description_pt_pt, row.description_en)
        for row in product_market_rows
    }

    total = _ZERO
    total_ipi = _ZERO
    order_items: list[OrderItem] = []
    for item_in in payload.items:
        product = product_map.get(item_in.product_code)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
        if product.id not in available_ids:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não está disponível neste mercado.")
        if product.id not in price_map:
            raise HTTPException(status_code=422, detail=f"Produto '{item_in.product_code}' não possui preço na lista {price_list.name}.")
        product_type = type_map.get(product.type)
        if market_code == "EU":
            vat_rate, vat_status = product_vat.get(product.id, (None, None))
            ipi_rate = _resolve_eu_vat(product.product_code, vat_rate, vat_status)
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
            qty=item_in.qty,
            unit_price=unit_price,
            discount=discount,
            ipi_rate=ipi_rate,
            ipi_value=ipi_value,
            tax_label=context.tax_label,
            currency=context.currency,
            observacao=product.observacao,
        ))

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
        total_value=total,
        total_ipi=total_ipi,
        total_with_ipi=total_with_ipi,
        notes=payload.notes,
        supersedes_order_id=source_order.id if source_order else None,
        revision_number=(source_order.revision_number + 1) if source_order else 1,
        items=order_items,
    )
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
    await db.refresh(order)
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
    if source.rep_signature is None and source.client_signature is None:
        raise HTTPException(status_code=409, detail="Somente pedido assinado exige revisão.")
    payload = OrderCreate(
        client_id=source.client_id, rep_id=source.rep_id, notes=source.notes,
        locale=source.locale if source.market_code == "EU" else None,
        supersedes_order_id=source.id,
        items=[OrderItemCreate(
            product_code=item.product_code, qty=item.qty,
            discount=item.discount, opt_categories=item.opt_categories,
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
            Order.total_value,
            Order.total_with_ipi,
            Order.is_finalized,
            Order.is_cancelled,
            Order.rep_signature.is_not(None).label("rep_signed"),
            Order.client_signature.is_not(None).label("client_signed"),
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
    if order.rep_signature is not None or order.client_signature is not None:
        raise HTTPException(status_code=409, detail="Pedido assinado é imutável. Crie uma revisão para corrigir os termos.")
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

    if payload.items is not None:
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
            db, [i.product_code for i in payload.items], principal.code
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
            if product.id not in available_ids:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não está disponível neste mercado.")
            if product.id not in price_map:
                raise HTTPException(status_code=422, detail=f"Produto '{item_in.product_code}' não possui preço na lista {price_list.name}.")
            product_type = type_map.get(product.type)
            if order.market_code == "EU":
                vat_rate, vat_status = product_vat.get(product.id, (None, None))
                ipi_rate = _resolve_eu_vat(product.product_code, vat_rate, vat_status)
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
                qty=item_in.qty,
                unit_price=unit_price,
                discount=discount,
                ipi_rate=ipi_rate,
                ipi_value=ipi_value,
                tax_label="IVA" if order.market_code == "EU" else "IPI",
                currency=order.currency,
                observacao=product.observacao,
            ))

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
    ))
    await db.execute(update(SignatureInvitation).where(
        SignatureInvitation.order_id == order.id,
        SignatureInvitation.consumed_at.is_(None),
        SignatureInvitation.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(timezone.utc)))
    await touch_client_activity(db, order.client_id)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("Falha ao editar pedido: id=%s user=%s", order_id, current_user.id, exc_info=True)
        raise HTTPException(status_code=500, detail="Falha ao salvar as alterações do pedido. Tente novamente.")
    await db.refresh(order)
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
    if order.rep_signature is not None or order.client_signature is not None:
        raise HTTPException(status_code=409, detail="Pedido assinado é imutável. Crie uma revisão para corrigir os termos.")
    terminal_at = datetime.now(timezone.utc)
    order.is_finalized = True
    order.finalized_at = terminal_at
    order.source_version += 1
    order.document_version += 1
    if payload.external_code:
        order.external_code = payload.external_code
    await db.execute(update(SignatureInvitation).where(
        SignatureInvitation.order_id == order.id,
        SignatureInvitation.consumed_at.is_(None),
        SignatureInvitation.revoked_at.is_(None),
    ).values(revoked_at=terminal_at))
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="finalized",
        details=f"código externo: {payload.external_code}" if payload.external_code else None,
    ))
    await touch_client_activity(db, order.client_id, terminal_at)
    await db.commit()
    await db.refresh(order)
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
    if order.rep_signature is not None or order.client_signature is not None:
        raise HTTPException(status_code=409, detail="Pedido assinado é imutável. Crie uma revisão para corrigir os termos.")
    terminal_at = datetime.now(timezone.utc)
    order.is_cancelled = True
    order.cancelled_at = terminal_at
    order.source_version += 1
    order.document_version += 1
    await db.execute(update(SignatureInvitation).where(
        SignatureInvitation.order_id == order.id,
        SignatureInvitation.consumed_at.is_(None),
        SignatureInvitation.revoked_at.is_(None),
    ).values(revoked_at=terminal_at))
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="cancelled",
        details=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
    ))
    await touch_client_activity(db, order.client_id, terminal_at)
    await db.commit()
    await db.refresh(order)
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


@router.get("/signature-audit")
async def signature_audit(
    skip: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=100, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    if principal.actor.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Auditoria de assinatura exige admin do mercado.")
    rows = (await db.execute(
        select(Order, OrderSignatureEvidence)
        .join(OrderSignatureEvidence, OrderSignatureEvidence.order_id == Order.id)
        .where(Order.market_code == principal.code)
        .order_by(Order.id, OrderSignatureEvidence.signer_kind)
        .offset(skip).limit(limit)
    )).all()
    result = []
    for order, evidence in rows:
        signature = order.client_signature if evidence.signer_kind == "client" else order.rep_signature
        current_hash = _order_document_hash(order) if evidence.document_hash else None
        signature_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest() if signature else None
        if evidence.verification_status == "unverified":
            status_value = "legacy_unverified"
        elif (evidence.document_hash is not None
              and evidence.signature_hash is not None
              and signature is not None
              and evidence.document_version == order.document_version
              and evidence.document_hash == current_hash
              and evidence.signature_hash == signature_hash):
            status_value = "matched"
        else:
            status_value = "divergent"
        result.append({
            "order_id": order.id, "signer_kind": evidence.signer_kind,
            "verification_status": status_value,
            "document_version": evidence.document_version,
            "signed_at": evidence.signed_at,
            "method": evidence.method,
            "submitted_by_user_id": evidence.submitted_by_user_id,
        })
    return result


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
    if order.rep_signature is not None or order.client_signature is not None:
        raise HTTPException(status_code=409, detail="Pedido assinado não pode ser excluído.")

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


class SignatureInviteIssue(BaseModel):
    confirmed_email: EmailStr
    verification_method: Literal["phone_callback", "existing_contract", "in_person"]


@router.post("/{order_id}/generate-sign-token", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def generate_sign_token(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    body: SignatureInviteIssue,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    _require_electronic_signatures_enabled()
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Convite de assinatura exige administrador do mercado.")
    if not invitation_delivery_ready():
        raise HTTPException(status_code=503, detail="Envio de convites não configurado.")
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.market_code == principal.code).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser assinado.")
    if order.client_signature:
        raise HTTPException(status_code=409, detail="Pedido já foi assinado pelo cliente.")
    client = (await db.execute(select(Client).where(
        Client.id == order.client_id, Client.market_code == principal.code,
    ))).scalar_one_or_none()
    recipient = str(body.confirmed_email).strip().lower()
    if client is None or not client.email or client.email.strip().lower() != recipient:
        raise HTTPException(status_code=422, detail="Confirme o e-mail atual do titular no cadastro.")

    now = datetime.now(timezone.utc)
    await db.execute(
        update(SignatureInvitation)
        .where(
            SignatureInvitation.order_id == order.id,
            SignatureInvitation.consumed_at.is_(None),
            SignatureInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token = generate_sign_invitation_token()
    invitation = SignatureInvitation(
        order_id=order.id,
        client_id=order.client_id,
        token_hash=hash_sign_invitation_token(token),
        document_hash=_order_document_hash(order),
        document_version=order.document_version,
        recipient_email=recipient,
        verified_by_user_id=current_user.id,
        verification_method=body.verification_method,
        issued_by=current_user.id,
        expires_at=sign_invitation_expiry(),
    )
    db.add(invitation)
    await db.commit()
    try:
        await send_signature_invitation(recipient, order.code, token)
    except Exception:
        logger.warning("Falha no envio de convite de assinatura: invitation_id=%s", invitation.id)
        invitation.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=503, detail="Não foi possível enviar o convite de assinatura.")
    invitation.sent_at = datetime.now(timezone.utc)
    await touch_client_activity(db, order.client_id, invitation.sent_at)
    await db.commit()
    return {"status": "sent", "recipient_email": recipient}


class VerifySignTokenPayload(BaseModel):
    token: str = Field(..., min_length=32, max_length=512)


# POST com token no body — token em querystring ficaria gravado nos access logs (V-04b)
@router.post("/verify-sign-token")
@limiter.limit("20/minute")
async def verify_sign_token(
    request: Request,
    response: Response,
    body: VerifySignTokenPayload,
    db: AsyncSession = Depends(get_db_session),
):
    _require_electronic_signatures_enabled()
    invitation = (
        await db.execute(
            select(SignatureInvitation).where(
                SignatureInvitation.token_hash == hash_sign_invitation_token(body.token)
            )
        )
    ).scalar_one_or_none()
    if not _invitation_is_valid(invitation):
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    result = await db.execute(select(Order).where(Order.id == invitation.order_id))
    order = result.scalar_one_or_none()
    if (not order or order.is_cancelled
            or invitation.document_version != order.document_version
            or invitation.document_hash != _order_document_hash(order)):
        if invitation:
            invitation.revoked_at = datetime.now(timezone.utc)
            await db.commit()
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one_or_none()
    if (client is None or not client.email
            or client.email.strip().lower() != invitation.recipient_email):
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    return {
        "order_code": order.code,
        "total_value": float(order.total_value),
        "is_signed": order.client_signature is not None,
        "document_hash": invitation.document_hash,
        "document": _order_document_content(order),
    }


_MAX_SIG_SIZE = 500_000  # ~375 KB PNG descomprimida


class SignPayload(BaseModel):
    signature: str

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        if len(v) > _MAX_SIG_SIZE:
            raise ValueError("Assinatura excede o tamanho máximo permitido.")
        if not v.startswith("data:image/png;base64,"):
            raise ValueError("Formato de assinatura inválido. Esperado PNG em base64.")
        return v


class SignWithTokenPayload(SignPayload):
    token: str = Field(..., min_length=32, max_length=512)
    document_hash: str = Field(..., min_length=64, max_length=64)


@router.post("/{order_id}/sign-representative")
async def sign_representative(
    order_id: uuid.UUID,
    payload: SignPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    _require_electronic_signatures_enabled()
    if current_user.role != UserRole.representante:
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
    if order.rep_signature:
        raise HTTPException(status_code=409, detail="Assinatura do representante já registrada.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser assinado.")
    order.rep_signature = payload.signature
    _record_signature(db, order, signer_kind="representative", signature=payload.signature,
                      method="authenticated", submitted_by_user_id=current_user.id)
    await touch_client_activity(db, order.client_id)
    await db.commit()
    return {"success": True}


@router.post("/{order_id}/sign-client")
async def sign_client(
    order_id: uuid.UUID,
    payload: SignPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    _require_electronic_signatures_enabled()
    if not is_client_account(current_user):
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
    if order.client_signature:
        raise HTTPException(status_code=409, detail="Assinatura do cliente já registrada.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser assinado.")
    order.client_signature = payload.signature
    _record_signature(db, order, signer_kind="client", signature=payload.signature,
                      method="authenticated", submitted_by_user_id=current_user.id)
    await db.execute(update(SignatureInvitation).where(
        SignatureInvitation.order_id == order.id,
        SignatureInvitation.consumed_at.is_(None),
        SignatureInvitation.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(timezone.utc)))
    await touch_client_activity(db, order.client_id)
    await db.commit()
    return {"success": True}


@router.post("/{order_id}/notify-client", status_code=status.HTTP_204_NO_CONTENT)
async def notify_client(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    _require_electronic_signatures_enabled()
    if current_user.role not in {UserRole.admin, UserRole.representante}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(select(Order).where(
        Order.id == order_id,
        *_order_visibility_filters(current_user),
    ))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    client_user = (await db.execute(
        select(User)
        .join(UserMarket, UserMarket.user_id == User.id)
        .where(
            UserMarket.market_code == order.market_code,
            UserMarket.role == UserRole.cliente.value,
            UserMarket.status == "active",
            UserMarket.linked_client_id == order.client_id,
            User.is_active.is_(True),
        )
        .order_by(User.id)
        .limit(1)
    )).scalar_one_or_none()
    if not client_user:
        raise HTTPException(status_code=404, detail="Cliente não possui conta ativa no sistema.")
    db.add(Notification(
        id=uuid.uuid4(),
        market_code=order.market_code,
        user_id=client_user.id,
        message=f"Você tem um contrato pendente de assinatura para o pedido {order.code}.",
    ))
    await touch_client_activity(db, order.client_id)
    await db.commit()


@router.post("/sign-with-token")
@limiter.limit("10/minute")
async def sign_with_token(
    request: Request,
    response: Response,
    payload: SignWithTokenPayload,
    db: AsyncSession = Depends(get_db_session),
):
    _require_electronic_signatures_enabled()
    candidate = (
        await db.execute(
            select(SignatureInvitation.id, SignatureInvitation.order_id)
            .where(
                SignatureInvitation.token_hash == hash_sign_invitation_token(payload.token)
            )
        )
    ).one_or_none()
    if candidate is None:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    # Ordem de locks idêntica à emissão: pedido antes do convite.
    result = await db.execute(
        select(Order).where(Order.id == candidate.order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    invitation = (await db.execute(select(SignatureInvitation).where(
        SignatureInvitation.id == candidate.id,
        SignatureInvitation.token_hash == hash_sign_invitation_token(payload.token),
    ).with_for_update())).scalar_one_or_none()
    if not _invitation_is_valid(invitation):
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if not order or order.is_cancelled or invitation.client_id != order.client_id:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one_or_none()
    if (client is None or not client.email
            or client.email.strip().lower() != invitation.recipient_email):
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if (payload.document_hash != invitation.document_hash
            or invitation.document_version != order.document_version
            or invitation.document_hash != _order_document_hash(order)):
        invitation.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    if order.client_signature:
        raise HTTPException(status_code=409, detail="Pedido já foi assinado.")

    order.client_signature = payload.signature
    _record_signature(db, order, signer_kind="client", signature=payload.signature,
                      method="emailed_token", invitation_id=invitation.id)
    invitation.consumed_at = datetime.now(timezone.utc)
    await touch_client_activity(db, order.client_id, invitation.consumed_at)
    await db.commit()
    return {"success": True}
