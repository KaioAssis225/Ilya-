import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.client import Client
from app.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientUpdate, ClientRead

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

_ADMIN = Depends(require_roles(UserRole.admin))


def _rep_guard(client: Client, current_user: User) -> None:
    if current_user.role == UserRole.representante and client.rep_id != current_user.rep_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este cliente.")


async def _linked_ids(db: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Returns the subset of entity IDs that already have a linked user."""
    if not ids:
        return set()
    result = await db.execute(select(User.linked_id).where(User.linked_id.in_(ids)))
    return {row[0] for row in result.fetchall() if row[0] is not None}


def _with_has_user(client: Client, linked: set[uuid.UUID]) -> ClientRead:
    r = ClientRead.model_validate(client)
    return r.model_copy(update={"has_user": client.id in linked})


@router.get("", response_model=List[ClientRead])
async def list_clients(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.representante:
        result = await db.execute(
            select(Client)
            .where(Client.rep_id == current_user.rep_id)
            .offset(skip).limit(limit)
        )
    else:
        result = await db.execute(select(Client).offset(skip).limit(limit))
    clients = result.scalars().all()
    linked = await _linked_ids(db, [c.id for c in clients])
    return [_with_has_user(c, linked) for c in clients]


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = Client(**payload.model_dump())
    if current_user.role == UserRole.representante:
        client.rep_id = current_user.rep_id
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ClientRead.model_validate(client)


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
    _rep_guard(client, current_user)
    linked = await _linked_ids(db, [client.id])
    return _with_has_user(client, linked)


@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    _rep_guard(client, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.commit()
    await db.refresh(client)
    linked = await _linked_ids(db, [client.id])
    return _with_has_user(client, linked)


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
