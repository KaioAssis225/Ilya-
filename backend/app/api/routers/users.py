import re
import secrets
import uuid
import unicodedata
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_, select, update

from app.api.deps import get_db_session, get_current_user, require_roles
from app.core.security import hash_password, validate_password_strength
from app.core.search import literal_contains_pattern
from app.models.user import User, UserRole
from app.models.client import Client
from app.models.representative import Representative
from app.models.refresh_token import RefreshToken
from app.schemas.auth import UserRead, UserCreate, UserUpdate, UserPasswordReset, UserCreateResponse

router = APIRouter(prefix="/api/v1/users", tags=["users"])
_admin_only = require_roles(UserRole.admin)


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


async def _validated_rep_assignment(
    role: UserRole,
    rep_id: uuid.UUID | None,
    db: AsyncSession,
) -> uuid.UUID | None:
    if role != UserRole.representante:
        return None
    if not rep_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Usuário representante precisa estar vinculado a um representante.",
        )
    exists = (
        await db.execute(
            select(Representative.id)
            .where(Representative.id == rep_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Representante vinculado não encontrado.",
        )
    return rep_id


@router.get("", response_model=list[UserRead])
async def list_users(
    response: Response,
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    include_total: bool = Query(default=True),
    sort_by: Literal[
        "full_name",
        "email",
        "role",
        "is_active",
    ] = Query(default="full_name"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    filters = []
    search = q.strip() if q else ""
    if search:
        search_pattern = literal_contains_pattern(search)
        filters.append(
            or_(
                User.full_name.ilike(search_pattern, escape="\\"),
                User.email.ilike(search_pattern, escape="\\"),
                User.username.ilike(search_pattern, escape="\\"),
            )
        )

    sort_column = {
        "full_name": User.full_name,
        "email": User.email,
        "role": User.role,
        "is_active": User.is_active,
    }[sort_by]
    order_expression = (
        sort_column.desc()
        if sort_dir == "desc"
        else sort_column.asc()
    )
    id_order = User.id.desc() if sort_dir == "desc" else User.id.asc()

    total: int | None = None
    if include_total:
        total = (
            await db.execute(
                select(func.count()).select_from(User).where(*filters)
            )
        ).scalar_one()
    result = await db.execute(
        select(User)
        .where(*filters)
        .order_by(order_expression, id_order)
        .offset(skip)
        .limit(limit if include_total else limit + 1)
    )
    loaded_users = list(result.scalars().all())
    users = loaded_users[:limit]
    has_more = (
        skip + len(users) < total
        if total is not None
        else len(loaded_users) > limit
    )
    if total is not None:
        response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(users))
    return users


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    # BUG-03 (Bloco 88): mesma política de complexidade do change-password
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if body.role == UserRole.cliente:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Contas de cliente devem ser criadas a partir do cadastro do cliente.",
        )
    normalized_email = str(body.email).lower()
    existing = await db.execute(
        select(User.id)
        .where(func.lower(User.email) == normalized_email)
        .limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado.")
    rep_id = await _validated_rep_assignment(
        body.role,
        body.rep_id,
        db,
    )
    user = User(
        email=normalized_email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        rep_id=rep_id,
        linked_id=rep_id,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "E-mail ou representante já vinculado a outra conta.",
        )
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
    submitted = body.model_dump(exclude_unset=True)
    changes = {
        field: value
        for field, value in submitted.items()
        if value is not None or field == "rep_id"
    }
    new_email = changes.get("email")
    if new_email:
        normalized_email = str(new_email).lower()
        duplicate_email = (
            await db.execute(
                select(User.id)
                .where(
                    func.lower(User.email) == normalized_email,
                    User.id != user.id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_email:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "E-mail já cadastrado.",
            )
        changes["email"] = normalized_email
    target_role = changes.get("role", user.role)
    target_rep_id = changes.get("rep_id", user.rep_id)
    changes["rep_id"] = await _validated_rep_assignment(
        target_role,
        target_rep_id,
        db,
    )
    if target_role == UserRole.representante:
        changes["linked_id"] = changes["rep_id"]
    elif target_role == UserRole.cliente:
        if user.role == UserRole.representante or user.linked_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Vincule a conta a um cliente pelo fluxo de cadastro.",
            )
        changes["linked_id"] = user.linked_id
    elif user.role == UserRole.representante:
        changes["linked_id"] = None
    elif target_role == UserRole.vendedor:
        changes["linked_id"] = user.linked_id
    else:
        changes["linked_id"] = None
    security_changed = any(
        field in changes and changes[field] != getattr(user, field)
        for field in ("role", "rep_id", "linked_id", "is_active")
    )
    for field, value in changes.items():
        setattr(user, field, value)
    if security_changed:
        user.auth_version += 1
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "E-mail ou representante já vinculado a outra conta.",
        )
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    body: UserPasswordReset,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    # BUG-03 (Bloco 88): reset administrativo também exige senha forte
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    user.hashed_password = hash_password(body.new_password)
    user.auth_version += 1
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )
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
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )
    await db.delete(user)
    await db.commit()


@router.post("/from-client/{client_id}", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
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

    if (
        current.role == UserRole.representante
        and (
            current.rep_id is None
            or client.rep_id != current.rep_id
        )
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso negado a este cliente.")

    linked_result = await db.execute(select(User).where(User.linked_id == client_id))
    if linked_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cliente já possui usuário cadastrado.")

    base_username = _normalize_username(client.name)
    username = await _resolve_unique_username(base_username, db)

    synthetic_email = f"{username}@clientes.ilya.internal"
    temp_password = secrets.token_urlsafe(9)

    user = User(
        email=synthetic_email,
        username=username,
        hashed_password=hash_password(temp_password),
        full_name=client.name,
        role=UserRole.cliente,  # SEC-01: conta de cliente-final, sem acesso de operador
        must_change_password=True,
        linked_id=client_id,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este cliente já possui uma conta ou o usuário acabou de ser criado.",
        )
    await db.refresh(user)
    return UserCreateResponse(
        id=user.id,
        username=user.username or '',
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        temp_password=temp_password,
    )


@router.post("/from-rep/{rep_id}", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user_from_rep(
    rep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(_admin_only),
):
    rep_result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = rep_result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Representante não encontrado.")

    linked_result = await db.execute(
        select(User.id).where(
            or_(
                User.linked_id == rep_id,
                User.rep_id == rep_id,
            )
        )
    )
    if linked_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Este representante já possui usuário cadastrado.")

    base_username = _normalize_username(rep.name)
    username = await _resolve_unique_username(base_username, db)

    synthetic_email = f"{username}@reps.ilya.internal"
    temp_password = secrets.token_urlsafe(9)

    user = User(
        email=synthetic_email,
        username=username,
        hashed_password=hash_password(temp_password),
        full_name=rep.name,
        role=UserRole.representante,
        rep_id=rep_id,
        must_change_password=True,
        linked_id=rep_id,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este representante já possui uma conta ou o usuário acabou de ser criado.",
        )
    await db.refresh(user)
    return UserCreateResponse(
        id=user.id,
        username=user.username or '',
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        temp_password=temp_password,
    )
