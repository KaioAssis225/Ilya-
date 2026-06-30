import re
import uuid
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.client import Client
from app.models.representative import Representative
from app.schemas.auth import UserRead, UserCreate, UserUpdate, UserPasswordReset

router = APIRouter(prefix="/api/v1/users", tags=["users"])
_admin_only = require_roles(UserRole.admin)

DEFAULT_PASSWORD = "senhailya"


def _normalize_username(full_name: str) -> str:
    nfkd = unicodedata.normalize('NFKD', full_name)
    ascii_str = nfkd.encode('ascii', 'ignore').decode('ascii')
    parts = re.sub(r'[^a-z0-9 ]', '', ascii_str.lower()).split()
    if len(parts) >= 2:
        base = parts[0] + parts[-1]
    elif parts:
        base = parts[0]
    else:
        base = 'usuario'
    return base[:50]


async def _resolve_unique_username(base: str, db: AsyncSession) -> str:
    username = base
    counter = 2
    while True:
        existing = await db.execute(select(User).where(User.username == username))
        if not existing.scalar_one_or_none():
            return username
        username = f"{base}{counter}"
        counter += 1


@router.get("", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    result = await db.execute(select(User).order_by(User.full_name))
    return result.scalars().all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado.")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        rep_id=body.rep_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
    current: User = Depends(_admin_only),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    body: UserPasswordReset,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current: User = Depends(_admin_only),
):
    if user_id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não é possível excluir o próprio usuário.")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    await db.delete(user)
    await db.commit()


@router.post("/from-client/{client_id}", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user_from_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current: User = Depends(get_current_user),
):
    if current.role not in (UserRole.admin, UserRole.representante):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operação não permitida para o seu nível de acesso.")

    client_result = await db.execute(select(Client).where(Client.id == client_id))
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")

    if current.role == UserRole.representante and client.rep_id != current.rep_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso negado a este cliente.")

    linked_result = await db.execute(select(User).where(User.linked_id == client_id))
    if linked_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cliente já possui usuário cadastrado.")

    base_username = _normalize_username(client.name)
    username = await _resolve_unique_username(base_username, db)

    synthetic_email = f"{username}@clientes.ilya.internal"

    user = User(
        email=synthetic_email,
        username=username,
        hashed_password=hash_password(DEFAULT_PASSWORD),
        full_name=client.name,
        role=UserRole.vendedor,
        must_change_password=True,
        linked_id=client_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/from-rep/{rep_id}", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user_from_rep(
    rep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    rep_result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = rep_result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Representante não encontrado.")

    linked_result = await db.execute(select(User).where(User.linked_id == rep_id))
    if linked_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Este representante já possui usuário cadastrado.")

    base_username = _normalize_username(rep.name)
    username = await _resolve_unique_username(base_username, db)

    synthetic_email = f"{username}@reps.ilya.internal"

    user = User(
        email=synthetic_email,
        username=username,
        hashed_password=hash_password(DEFAULT_PASSWORD),
        full_name=rep.name,
        role=UserRole.representante,
        rep_id=rep_id,
        must_change_password=True,
        linked_id=rep_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
