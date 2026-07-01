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
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.user import User, UserRole
from app.models.notification import Notification
from app.schemas.order import OrderCreate, OrderRead
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

    client = (await db.execute(select(Client).where(Client.id == payload.client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    if payload.rep_id:
        rep = (await db.execute(select(Representative).where(Representative.id == payload.rep_id))).scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Representante não encontrado.")

    total = 0.0
    order_items: list[OrderItem] = []
    for item_in in payload.items:
        product = (await db.execute(
            select(Product).where(Product.product_code == item_in.product_code)
        )).scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail=f"Produto '{item_in.product_code}' não encontrado.")
        unit_price = float(product.price)
        subtotal = float(item_in.qty) * unit_price
        total += subtotal
        order_items.append(OrderItem(
            id=uuid.uuid4(),
            product_code=product.product_code,
            description=product.description,
            is_circular=product.is_circular,
            altura=product.altura,
            largura=product.largura,
            profundidade=product.profundidade,
            opt_aluminio=item_in.opt_aluminio,
            opt_madeira=item_in.opt_madeira,
            opt_tecido=item_in.opt_tecido,
            opt_couro=item_in.opt_couro,
            opt_corda=item_in.opt_corda,
            qty=item_in.qty,
            unit_price=unit_price,
        ))

    code, orc_id = await _next_code(db)
    order = Order(
        id=uuid.uuid4(),
        code=code,
        orc_id=orc_id,
        client_id=payload.client_id,
        rep_id=payload.rep_id,
        total_value=round(total, 2),
        notes=payload.notes,
        items=order_items,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    logger.info("Pedido criado: code=%s orc=%s total=%.2f user_id=%s", code, orc_id, order.total_value, current_user.id)
    return order


@router.get("", response_model=List[OrderRead])
async def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
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
async def verify_sign_token(
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
async def sign_with_token(
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
