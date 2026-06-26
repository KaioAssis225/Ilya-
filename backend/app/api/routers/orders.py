import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.order import Order, OrderItem
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import OrderCreate, OrderRead

logger = logging.getLogger("ilya.orders")
router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ANY = Depends(get_current_user)
_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


async def _next_code(db: AsyncSession) -> tuple[str, str]:
    result = await db.execute(select(func.count()).select_from(Order))
    n = (result.scalar() or 0) + 1
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
    if current_user.role not in [UserRole.admin, UserRole.vendedor, UserRole.representante]:
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
        unit_price = float(item_in.unit_price)
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
