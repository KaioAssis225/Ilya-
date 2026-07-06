import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.api.deps import get_db_session, get_current_user, require_roles
from app.core.limiter import limiter
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.product_type import ProductType
from app.models.user import User, UserRole
from app.models.notification import Notification
from app.schemas.order import OrderCreate, OrderRead, OrderListRead, OrderUpdate, OrderHistoryRead
from app.core.security import create_sign_token, decode_sign_token

logger = logging.getLogger("ilya.orders")
router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


async def _next_code(db: AsyncSession) -> tuple[str, str]:
    # nextval é atômico no PostgreSQL — elimina race condition de COUNT(*) (V-01)
    n = (await db.execute(text("SELECT nextval('order_seq')"))).scalar()
    return f"PED-{n:04d}", f"ORC-{n:04d}"


async def _load_products_and_types(
    db: AsyncSession, codes: list[str]
) -> tuple[dict[str, Product], dict[str, ProductType]]:
    """Carrega produtos e seus tipos em 2 queries (evita N+1 por item — V-B1)."""
    products = (await db.execute(
        select(Product).where(Product.product_code.in_(codes))
    )).scalars().all()
    product_map = {p.product_code: p for p in products}

    type_names = {p.type for p in products}
    types = (await db.execute(
        select(ProductType).where(ProductType.name.in_(type_names))
    )).scalars().all() if type_names else []
    type_map = {t.name: t for t in types}
    return product_map, type_map


def _price_for_profile(product: Product, profile: str) -> float:
    """Preço faturado conforme o perfil do cliente (V-Bloco62)."""
    if profile == "corporativo":
        return float(product.price_corporativo)
    return float(product.price_lojista)


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
    _allowed_create = {UserRole.admin, UserRole.vendedor, UserRole.representante, UserRole.produtos}
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

    if current_user.role == UserRole.vendedor and payload.client_id != current_user.linked_id:
        # Cliente logado (V-Bloco66-RBAC): só pode criar pedido para si mesmo.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação não permitida para este cliente.")

    client = (await db.execute(select(Client).where(Client.id == payload.client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    if payload.rep_id:
        rep = (await db.execute(select(Representative).where(Representative.id == payload.rep_id))).scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Representante não encontrado.")

    # Batch-fetch de produtos e tipos — elimina N+1 (V-B1)
    product_map, type_map = await _load_products_and_types(db, [i.product_code for i in payload.items])
    profile = client.price_profile  # faturamento pelo perfil do cliente (V-Bloco62)

    total = 0.0
    total_ipi = 0.0
    order_items: list[OrderItem] = []
    for item_in in payload.items:
        product = product_map.get(item_in.product_code)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
        unit_price = _price_for_profile(product, profile)
        discount = float(item_in.discount or 0)
        effective_price = unit_price * (1 - discount / 100)
        subtotal = float(item_in.qty) * effective_price
        total += subtotal

        product_type = type_map.get(product.type)
        ipi_rate = float(product_type.group.ipi) if product_type and product_type.group else 0.0
        ipi_value = round(subtotal * ipi_rate / 100, 2)
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

    code, orc_id = await _next_code(db)
    order = Order(
        id=uuid.uuid4(),
        code=code,
        orc_id=orc_id,
        client_id=payload.client_id,
        rep_id=payload.rep_id,
        total_value=round(total, 2),
        total_ipi=round(total_ipi, 2),
        total_with_ipi=round(total + total_ipi, 2),
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
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, le=5000),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.representante:
        result = await db.execute(
            select(Order).where(Order.rep_id == current_user.rep_id)
            .order_by(Order.created_at.desc()).offset(skip).limit(limit)
        )
    elif current_user.role == UserRole.vendedor and current_user.linked_id:
        result = await db.execute(
            select(Order).where(Order.client_id == current_user.linked_id)
            .order_by(Order.created_at.desc()).offset(skip).limit(limit)
        )
    else:
        result = await db.execute(
            select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit)
        )
    return result.scalars().all()


@router.get("/history", response_model=List[OrderHistoryRead])
async def list_global_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.vendedor}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(
        select(OrderHistory).order_by(OrderHistory.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.put("/{order_id}", response_model=OrderRead)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    _allowed = {UserRole.admin, UserRole.vendedor, UserRole.representante}
    if current_user.role not in _allowed:
        raise HTTPException(status_code=403, detail="Operação não permitida.")

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já finalizado e não pode ser editado.")
    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")

    changes: list[str] = []

    if payload.notes is not None and payload.notes != order.notes:
        changes.append(f"observações alteradas")
        order.notes = payload.notes

    if payload.rep_id is not None and payload.rep_id != order.rep_id:
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

        total = 0.0
        total_ipi = 0.0
        new_items: list[OrderItem] = []
        for item_in in payload.items:
            product = product_map.get(item_in.product_code)
            if not product:
                raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
            unit_price = _price_for_profile(product, profile)
            discount = float(item_in.discount or 0)
            effective_price = unit_price * (1 - discount / 100)
            subtotal = float(item_in.qty) * effective_price
            total += subtotal

            product_type = type_map.get(product.type)
            ipi_rate = float(product_type.group.ipi) if product_type and product_type.group else 0.0
            ipi_value = round(subtotal * ipi_rate / 100, 2)
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

        old_total = float(order.total_value)
        order.total_value = round(total, 2)
        order.total_ipi = round(total_ipi, 2)
        order.total_with_ipi = round(total + total_ipi, 2)
        if abs(old_total - round(total, 2)) > 0.01:
            changes.append(f"total: R$ {old_total:.2f} → R$ {round(total, 2):.2f}")
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
    external_code: str | None = None


@router.post("/{order_id}/finalize", response_model=OrderRead)
async def finalize_order(
    order_id: uuid.UUID,
    payload: FinalizePayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.vendedor}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if order.is_finalized:
        raise HTTPException(status_code=409, detail="Pedido já está finalizado.")
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
    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if current_user.role == UserRole.vendedor and current_user.linked_id and order.client_id != current_user.linked_id:
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
    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if current_user.role == UserRole.vendedor and current_user.linked_id and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(select(Order).where(Order.id == order_id))
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
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if current_user.role == UserRole.vendedor and current_user.linked_id and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")

    token = create_sign_token(str(order.id), str(order.client_id))
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

    return {"token": token, "url": url, "expires_in": 600}


@router.get("/verify-sign-token")
@limiter.limit("20/minute")
async def verify_sign_token(
    request: Request,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    payload = decode_sign_token(token)
    if not payload:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    try:
        order_id = uuid.UUID(payload["order_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Token inválido.")

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

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
        if not v.startswith("data:image/"):
            raise ValueError("Formato de assinatura inválido.")
        return v


@router.post("/{order_id}/sign-representative")
async def sign_representative(
    order_id: uuid.UUID,
    payload: SignPayload,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.representante}:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
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
    is_client = current_user.role == UserRole.vendedor and current_user.linked_id is not None
    is_rep = current_user.role == UserRole.representante
    if current_user.role != UserRole.admin and not is_client and not is_rep:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if is_client and order.client_id != current_user.linked_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
    if is_rep and order.rep_id != current_user.rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este pedido.")
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
    if current_user.role == UserRole.representante and order.rep_id != current_user.rep_id:
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


class SignWithTokenPayload(BaseModel):
    token: str
    signature: str

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        if len(v) > _MAX_SIG_SIZE:
            raise ValueError("Assinatura excede o tamanho máximo permitido.")
        if not v.startswith("data:image/"):
            raise ValueError("Formato de assinatura inválido.")
        return v


@router.post("/sign-with-token")
@limiter.limit("10/minute")
async def sign_with_token(
    request: Request,
    payload: SignWithTokenPayload,
    db: AsyncSession = Depends(get_db_session),
):
    decoded = decode_sign_token(payload.token)
    if not decoded:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    try:
        order_id = uuid.UUID(decoded["order_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Token inválido.")

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    if order.client_signature:
        raise HTTPException(status_code=409, detail="Pedido já foi assinado.")

    order.client_signature = payload.signature
    await db.commit()
    return {"success": True}
