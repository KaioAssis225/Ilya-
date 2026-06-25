import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.order import Order, OrderItem
from app.models.client import Client
from app.models.representative import Representative
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import OrderCreate, OrderRead

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
    _: User = _ADMIN_VENDEDOR,
):
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
        subtotal = float(item_in.qty) * float(item_in.unit_price)
        total += subtotal
        order_items.append(OrderItem(
            id=uuid.uuid4(),
            product_code=product.product_code,
            description=product.description,
            altura=product.altura,
            largura=product.largura,
            profundidade=product.profundidade,
            opt_aluminio=product.opt_aluminio,
            opt_tecido=product.opt_tecido,
            opt_corda=product.opt_corda,
            qty=item_in.qty,
            unit_price=item_in.unit_price,
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
    return order


@router.get("", response_model=List[OrderRead])
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit)
    # Multi-tenancy: representantes só veem seus próprios pedidos
    if current_user.role == UserRole.representante:
        stmt = stmt.where(Order.rep_id == current_user.rep_id)
    result = await db.execute(stmt)
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


@router.delete("/{id_or_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    id_or_code: str,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    order = await _get_order(db, id_or_code)
    await db.delete(order)
    await db.commit()
