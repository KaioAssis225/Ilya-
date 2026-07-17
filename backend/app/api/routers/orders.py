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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, text, tuple_, update
from sqlalchemy.orm import load_only, noload, selectinload

from app.api.deps import (
    get_db_session,
    get_current_user,
    require_roles,
    is_client_account,
    is_internal_operator,
)
from app.core.limiter import limiter
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
from app.schemas.order import OrderCreate, OrderRead, OrderListRead, OrderUpdate, OrderHistoryRead
from app.core.security import (
    SIGN_TOKEN_TTL_MINUTES,
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


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: object) -> Decimal:
    return _decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _ensure_total_capacity(*values: Decimal) -> None:
    if any(abs(value) > _MAX_ORDER_TOTAL for value in values):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valor total do pedido excede o limite financeiro permitido.",
        )


def _representative_cannot_access_order(
    current_user: User,
    order: Order,
) -> bool:
    return (
        current_user.role == UserRole.representante
        and (
            current_user.rep_id is None
            or order.rep_id != current_user.rep_id
        )
    )


def _order_document_hash(order: Order) -> str:
    content = {
        "order_id": str(order.id),
        "code": order.code,
        "client_id": str(order.client_id),
        "rep_id": str(order.rep_id) if order.rep_id else None,
        "total_value": str(order.total_value),
        "total_ipi": str(order.total_ipi),
        "total_with_ipi": str(order.total_with_ipi),
        "notes": order.notes,
        "items": [
            {
                "product_code": item.product_code,
                "description": item.description,
                "qty": item.qty,
                "unit_price": str(item.unit_price),
                "discount": str(item.discount),
                "ipi_rate": str(item.ipi_rate),
                "optionals": item.opt_categories,
            }
            for item in sorted(order.items, key=lambda current: str(current.id))
        ],
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _invitation_is_valid(invitation: SignatureInvitation | None) -> bool:
    if not invitation or invitation.consumed_at or invitation.revoked_at:
        return False
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at >= datetime.now(timezone.utc)


async def _next_code(db: AsyncSession) -> tuple[str, str]:
    # nextval é atômico no PostgreSQL — elimina race condition de COUNT(*) (V-01)
    n = (await db.execute(text("SELECT nextval('order_seq')"))).scalar()
    return f"PED-{n:04d}", f"ORC-{n:04d}"


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
    db: AsyncSession, codes: list[str]
) -> tuple[dict[str, Product], dict[str, ProductType]]:
    """Carrega produtos e seus tipos em 2 queries (evita N+1 por item — V-B1)."""
    products = (await db.execute(
        select(Product)
        .where(Product.product_code.in_(codes))
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
        .where(ProductType.name.in_(type_names))
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
    return _HUNDRED  # admin / produtos


def _validate_discount(
    discount: Decimal | float,
    max_discount: Decimal | float,
    product_code: str,
) -> None:
    discount_value = _decimal(discount)
    max_discount_value = _decimal(max_discount)
    if discount_value < _ZERO or discount_value > max_discount_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Desconto de {discount_value}% no item '{product_code}' excede o limite permitido ({max_discount_value}%) para o seu nível de acesso.",
        )


async def _get_order(db: AsyncSession, id_or_code: str) -> Order:
    try:
        oid = uuid.UUID(id_or_code)
        result = await db.execute(select(Order).where(Order.id == oid))
    except ValueError:
        upper = id_or_code.upper()
        if upper.startswith("ORC"):
            result = await db.execute(select(Order).where(Order.orc_id == upper))
        else:
            result = await db.execute(select(Order).where(Order.code == upper))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return order


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    _allowed_create = {UserRole.admin, UserRole.vendedor, UserRole.representante, UserRole.produtos, UserRole.cliente}
    if current_user.role not in _allowed_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação não permitida para o seu nível de acesso."
        )

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

    client = (await db.execute(select(Client).where(Client.id == payload.client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
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
        rep = (await db.execute(select(Representative).where(Representative.id == payload.rep_id))).scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Representante não encontrado.")

    max_discount = _resolve_max_discount(current_user, client, rep)

    # Batch-fetch de produtos e tipos — elimina N+1 (V-B1)
    product_map, type_map = await _load_products_and_types(db, [i.product_code for i in payload.items])
    profile = client.price_profile  # faturamento pelo perfil do cliente (V-Bloco62)

    total = _ZERO
    total_ipi = _ZERO
    order_items: list[OrderItem] = []
    for item_in in payload.items:
        product = product_map.get(item_in.product_code)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
        unit_price = _price_for_profile(product, profile)
        discount = _decimal(item_in.discount or _ZERO)
        _validate_discount(discount, max_discount, product.product_code)
        effective_price = unit_price * (_HUNDRED - discount) / _HUNDRED
        subtotal = _money(_decimal(item_in.qty) * effective_price)
        total += subtotal

        product_type = type_map.get(product.type)
        ipi_rate = (
            _decimal(product_type.group.ipi)
            if product_type and product_type.group
            else _ZERO
        )
        ipi_value = _money(subtotal * ipi_rate / _HUNDRED)
        total_ipi += ipi_value

        order_items.append(OrderItem(
            id=uuid.uuid4(),
            product_code=product.product_code,
            description=product.description,
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
            observacao=product.observacao,
        ))

    total = _money(total)
    total_ipi = _money(total_ipi)
    total_with_ipi = _money(total + total_ipi)
    _ensure_total_capacity(total, total_ipi, total_with_ipi)
    code, orc_id = await _next_code(db)
    order = Order(
        id=uuid.uuid4(),
        code=code,
        orc_id=orc_id,
        client_id=payload.client_id,
        rep_id=payload.rep_id,
        total_value=total,
        total_ipi=total_ipi,
        total_with_ipi=total_with_ipi,
        notes=payload.notes,
        items=order_items,
    )
    try:
        db.add(order)
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
    current_user: User = Depends(get_current_user),
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
            Order.client_id,
            Client.name.label("client_name"),
            Order.rep_id,
            Representative.name.label("rep_name"),
            Order.total_value,
            Order.total_with_ipi,
            Order.is_finalized,
            Order.is_cancelled,
            Order.created_at,
        )
        .select_from(Order)
        .join(Client, Client.id == Order.client_id)
        .outerjoin(Representative, Representative.id == Order.rep_id)
        .where(*conditions)
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
):
    if not (current_user.role == UserRole.admin or is_internal_operator(current_user)):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    stmt = select(OrderHistory)
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
):
    # Edição é operação de operador interno ou representante — cliente-final nunca edita pedido (SEC-02).
    if not (current_user.role in {UserRole.admin, UserRole.representante} or is_internal_operator(current_user)):
        raise HTTPException(status_code=403, detail="Operação não permitida.")

    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já finalizado e não pode ser editado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado e não pode ser editado.")
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")

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
                    Representative.id == payload.rep_id
                )
            )
        ).scalar_one_or_none()
        if not selected_rep:
            raise HTTPException(
                status_code=404,
                detail="Representante não encontrado.",
            )
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
            db, [i.product_code for i in payload.items]
        )
        client = (await db.execute(select(Client).where(Client.id == order.client_id))).scalar_one_or_none()
        profile = client.price_profile if client else "lojista"  # faturamento pelo perfil (V-Bloco62)
        rep = selected_rep
        if rep is None and order.rep_id:
            rep = (
                await db.execute(
                    select(Representative).where(
                        Representative.id == order.rep_id
                    )
                )
            ).scalar_one_or_none()
        max_discount = _resolve_max_discount(current_user, client, rep)

        total = _ZERO
        total_ipi = _ZERO
        new_items: list[OrderItem] = []
        for item_in in payload.items:
            product = product_map.get(item_in.product_code)
            if not product:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
            unit_price = _price_for_profile(product, profile)
            discount = _decimal(item_in.discount or _ZERO)
            _validate_discount(discount, max_discount, product.product_code)
            effective_price = unit_price * (_HUNDRED - discount) / _HUNDRED
            subtotal = _money(_decimal(item_in.qty) * effective_price)
            total += subtotal

            product_type = type_map.get(product.type)
            ipi_rate = (
                _decimal(product_type.group.ipi)
                if product_type and product_type.group
                else _ZERO
            )
            ipi_value = _money(subtotal * ipi_rate / _HUNDRED)
            total_ipi += ipi_value

            new_items.append(OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                product_code=product.product_code,
                description=product.description,
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
            changes.append(f"total: R$ {old_total:.2f} → R$ {total:.2f}")
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
    if not (current_user.role == UserRole.admin or is_internal_operator(current_user) or current_user.role == UserRole.representante):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    # Representante só finaliza os próprios pedidos (mesma regra do update_order)
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já está finalizado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido cancelado não pode ser finalizado.")
    order.is_finalized = True
    if payload.external_code:
        order.external_code = payload.external_code
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="finalized",
        details=f"código externo: {payload.external_code}" if payload.external_code else None,
    ))
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
    if not (current_user.role == UserRole.admin or is_internal_operator(current_user) or current_user.role == UserRole.representante):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    # Representante só cancela os próprios pedidos (mesma regra do update_order/finalize_order)
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido finalizado não pode ser cancelado.")
    if order.is_cancelled:
        raise HTTPException(status_code=409, detail="Pedido já está cancelado.")
    order.is_cancelled = True
    db.add(OrderHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=current_user.id,
        action="cancelled",
        details=payload.reason.strip() if payload.reason and payload.reason.strip() else None,
    ))
    await db.commit()
    await db.refresh(order)
    logger.info("Pedido cancelado: id=%s user=%s", order_id, current_user.id)
    return order


@router.get("/{order_id}/history", response_model=List[OrderHistoryRead])
async def get_order_history(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if is_client_account(current_user) and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    hist = await db.execute(
        select(OrderHistory).where(OrderHistory.order_id == order_id).order_by(OrderHistory.created_at.asc())
    )
    return hist.scalars().all()


@router.get("/{id_or_code}", response_model=OrderRead)
async def get_order(
    id_or_code: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    order = await _get_order(db, id_or_code)
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if is_client_account(current_user) and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    await db.delete(order)
    await db.commit()
    logger.warning("Pedido excluído: id=%s", order_id)


@router.post("/{order_id}/generate-sign-token")
@limiter.limit("5/minute")
async def generate_sign_token(
    request: Request,
    response: Response,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.client_signature:
        raise HTTPException(status_code=409, detail="Pedido já foi assinado pelo cliente.")

    if not (
        current_user.role in {UserRole.admin, UserRole.representante}
        or is_internal_operator(current_user)
    ):
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")

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
        issued_by=current_user.id,
        expires_at=sign_invitation_expiry(),
    )
    db.add(invitation)
    # Fragment (#) não é enviado ao servidor nem aparece em logs/Referer (V-04)
    url = f"/sign-contract#{token}"

    client_user = (await db.execute(
        select(User).where(User.linked_id == order.client_id, User.is_active.is_(True))
    )).scalar_one_or_none()

    if client_user:
        db.add(Notification(
            id=uuid.uuid4(),
            user_id=client_user.id,
            message=f"Você tem um contrato pendente de assinatura para o pedido {order.code}.",
        ))
    await db.commit()

    return {"token": token, "url": url, "expires_in": SIGN_TOKEN_TTL_MINUTES * 60}


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
    if not order or invitation.document_hash != _order_document_hash(order):
        if invitation:
            invitation.revoked_at = datetime.now(timezone.utc)
            await db.commit()
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    return {
        "order_code": order.code,
        "total_value": float(order.total_value),
        "is_signed": order.client_signature is not None,
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


@router.post("/{order_id}/sign-representative")
async def sign_representative(
    order_id: uuid.UUID,
    payload: SignPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.representante}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if order.rep_signature:
        raise HTTPException(status_code=409, detail="Assinatura do representante já registrada.")
    order.rep_signature = payload.signature
    await db.commit()
    return {"success": True}


@router.post("/{order_id}/sign-client")
async def sign_client(
    order_id: uuid.UUID,
    payload: SignPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    is_client = is_client_account(current_user)
    is_rep = current_user.role == UserRole.representante
    if current_user.role != UserRole.admin and not is_client and not is_rep:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if is_client and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if is_rep and _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if order.client_signature:
        raise HTTPException(status_code=409, detail="Assinatura do cliente já registrada.")
    order.client_signature = payload.signature
    await db.commit()
    return {"success": True}


@router.post("/{order_id}/notify-client", status_code=status.HTTP_204_NO_CONTENT)
async def notify_client(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.representante}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if _representative_cannot_access_order(current_user, order):
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    client_user = (await db.execute(
        select(User).where(
            User.linked_id == order.client_id,
            User.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not client_user:
        raise HTTPException(status_code=404, detail="Cliente não possui conta ativa no sistema.")
    db.add(Notification(
        id=uuid.uuid4(),
        user_id=client_user.id,
        message=f"Você tem um contrato pendente de assinatura para o pedido {order.code}.",
    ))
    await db.commit()


@router.post("/sign-with-token")
@limiter.limit("10/minute")
async def sign_with_token(
    request: Request,
    response: Response,
    payload: SignWithTokenPayload,
    db: AsyncSession = Depends(get_db_session),
):
    invitation = (
        await db.execute(
            select(SignatureInvitation)
            .where(
                SignatureInvitation.token_hash == hash_sign_invitation_token(payload.token)
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not _invitation_is_valid(invitation):
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    result = await db.execute(
        select(Order).where(Order.id == invitation.order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order or invitation.client_id != order.client_id:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
    if invitation.document_hash != _order_document_hash(order):
        invitation.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    if order.client_signature:
        raise HTTPException(status_code=409, detail="Pedido já foi assinado.")

    order.client_signature = payload.signature
    invitation.consumed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}
