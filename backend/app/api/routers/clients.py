import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.client import Client
from app.models.order import Order
from app.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientUpdate, ClientRead

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))


@router.get("", response_model=List[ClientRead])
async def list_clients(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    # HIGH-04: representante só vê clientes dos seus próprios pedidos
    if current_user.role == UserRole.representante:
        subq = select(Order.client_id).where(Order.rep_id == current_user.rep_id).distinct()
        result = await db.execute(
            select(Client).where(Client.id.in_(subq)).offset(skip).limit(limit)
        )
    else:
        result = await db.execute(select(Client).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    client = Client(**payload.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    # HIGH-04: representante só acessa clientes vinculados aos seus pedidos
    if current_user.role == UserRole.representante:
        linked = await db.execute(
            select(Order.id).where(Order.client_id == client_id, Order.rep_id == current_user.rep_id).limit(1)
        )
        if not linked.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Acesso negado a este cliente.")
    return client


@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.commit()
    await db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    await db.delete(client)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Este cliente possui pedidos vinculados no histórico comercial e seus dados "
                "fiscais/financeiros não podem ser fisicamente excluídos para conformidade fiscal. "
                "Solicite a anonimização dos dados de contato caso necessário."
            ),
        )
