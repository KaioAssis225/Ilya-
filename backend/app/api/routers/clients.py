import uuid
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select

import logging

from app.api.deps import get_db_session, get_current_user, require_roles, is_client_account
from app.core.search import literal_contains_pattern
from app.models.client import Client, anonymize_client_fields
from app.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientUpdate, ClientRead

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

logger = logging.getLogger("ilya.clients")

_ADMIN = Depends(require_roles(UserRole.admin))


def _rep_guard(client: Client, current_user: User) -> None:
    if (
        current_user.role == UserRole.representante
        and (
            current_user.rep_id is None
            or client.rep_id != current_user.rep_id
        )
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este cliente.")
    if is_client_account(current_user) and client.id != current_user.linked_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este cliente.")


async def _user_status(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[bool, bool]]:
    """Returns {linked_id: (has_user, user_validated)} for the given entity IDs."""
    if not ids:
        return {}
    result = await db.execute(
        select(
            User.linked_id,
            User.must_change_password,
            User.is_active,
        ).where(User.linked_id.in_(ids))
    )
    return {
        row[0]: (True, bool(row[2]) and not row[1])
        for row in result.fetchall()
        if row[0] is not None
    }


def _with_has_user(client: Client, status_map: dict[uuid.UUID, tuple[bool, bool]]) -> ClientRead:
    has_user, user_validated = status_map.get(client.id, (False, False))
    r = ClientRead.model_validate(client)
    return r.model_copy(update={"has_user": has_user, "user_validated": user_validated})


@router.get("", response_model=List[ClientRead])
async def list_clients(
    response: Response,
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=100, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    include_total: bool = Query(default=True),
    sort_by: Literal[
        "name",
        "email",
        "phone",
        "city",
        "state",
        "max_discount",
    ] = Query(default="name"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    filters = []
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            response.headers["X-Total-Count"] = "0"
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        filters.append(Client.rep_id == current_user.rep_id)
    elif is_client_account(current_user):
        filters.append(Client.id == current_user.linked_id)

    search = q.strip() if q else ""
    if search:
        search_pattern = literal_contains_pattern(search)
        filters.append(
            or_(
                Client.name.ilike(search_pattern, escape="\\"),
                Client.email.ilike(search_pattern, escape="\\"),
                Client.city.ilike(search_pattern, escape="\\"),
            )
        )

    sort_column = {
        "name": Client.name,
        "email": Client.email,
        "phone": Client.phone,
        "city": Client.city,
        "state": Client.state,
        "max_discount": Client.max_discount,
    }[sort_by]
    order_expression = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    id_order = Client.id.desc() if sort_dir == "desc" else Client.id.asc()

    total: int | None = None
    if include_total:
        total = (
            await db.execute(
                select(func.count()).select_from(Client).where(*filters)
            )
        ).scalar_one()
    result = await db.execute(
        select(Client)
        .where(*filters)
        .order_by(order_expression, id_order)
        .offset(skip)
        .limit(limit if include_total else limit + 1)
    )
    loaded_clients = list(result.scalars().all())
    clients = loaded_clients[:limit]
    has_more = (
        skip + len(clients) < total
        if total is not None
        else len(loaded_clients) > limit
    )
    if total is not None:
        response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(clients))
    linked = await _user_status(db, [c.id for c in clients])
    return [_with_has_user(c, linked) for c in clients]


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.representante)),
):
    data = payload.model_dump()
    duplicate_email = (
        await db.execute(
            select(Client.id).where(
                func.lower(Client.email) == str(payload.email).lower()
            ).limit(1)
        )
    ).scalar_one_or_none()
    if duplicate_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um cliente com este e-mail.",
        )
    if current_user.role not in (UserRole.admin, UserRole.cadastros, UserRole.produtos):
        data["max_discount"] = ClientCreate.model_fields["max_discount"].default
    client = Client(**data)
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "O usuário representante não possui um registro "
                    "de representante associado."
                ),
            )
        client.rep_id = current_user.rep_id
    db.add(client)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um cliente com este e-mail.",
        )
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
    linked = await _user_status(db, [client.id])
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
    update_data = payload.model_dump(exclude_unset=True)
    if current_user.role == UserRole.representante:
        update_data.pop("email", None)
        update_data.pop("price_profile", None)
    if current_user.role not in (UserRole.admin, UserRole.cadastros, UserRole.produtos):
        update_data.pop("max_discount", None)
    new_email = update_data.get("email")
    if new_email:
        duplicate_email = (
            await db.execute(
                select(Client.id).where(
                    func.lower(Client.email) == str(new_email).lower(),
                    Client.id != client.id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um cliente com este e-mail.",
            )
    for field, value in update_data.items():
        setattr(client, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um cliente com este e-mail.",
        )
    await db.refresh(client)
    linked = await _user_status(db, [client.id])
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


@router.post("/{client_id}/anonymize", status_code=status.HTTP_204_NO_CONTENT)
async def anonymize_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    """LGPD Art. 18, IV (via Art. 18 §1º — pedido do titular por outros canais):
    anonimiza um cliente que não possui conta no sistema, preservando o registro
    para integridade fiscal dos pedidos (Art. 16, I). Desativa a conta vinculada,
    caso exista."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    anonymize_client_fields(client)

    linked_user = (await db.execute(
        select(User).where(User.linked_id == client_id, User.is_active.is_(True))
    )).scalar_one_or_none()
    if linked_user:
        linked_user.is_active = False

    await db.commit()
    logger.info("Anonimização admin: client_id=%s por user_id=%s", client_id, current_user.id)
