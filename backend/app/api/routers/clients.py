import uuid
from datetime import datetime, timezone
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select

import logging

from app.api.deps import (
    COMMERCIAL_ROLES,
    get_db_session,
    get_current_user,
    require_directory_access,
    require_roles,
    is_client_account,
    sanitize_client_update_fields,
)
from app.core.search import literal_contains_pattern
from app.core.privacy_audit import record_privacy_event
from app.models.client import Client, anonymize_client_fields
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientUpdate, ClientRead

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

logger = logging.getLogger("ilya.clients")

_ADMIN = Depends(require_roles(UserRole.admin))


def _conflict_detail(error: IntegrityError) -> str:
    """Com duas restrições únicas na tabela, dizer sempre 'e-mail' mandaria o
    operador procurar o problema no campo errado."""
    if "cpf_cnpj" in str(error.orig):
        return "Já existe um cliente com este CPF/CNPJ."
    return "Já existe um cliente com este e-mail."

# Quem cadastra cliente. `cadastros` e `produtos` entram porque decidem a
# carteira (COMMERCIAL_ROLES) e o teto de desconto na edição — sem poder
# cadastrar, decidiam sobre um registro que não conseguiam criar. Constante
# nomeada para o teste conferir a coerência com COMMERCIAL_ROLES.
_CREATE_CLIENT_ROLES = (
    UserRole.admin,
    UserRole.vendedor,
    UserRole.representante,
    UserRole.cadastros,
    UserRole.produtos,
)


async def _validated_rep_id(
    rep_id: uuid.UUID | None,
    db: AsyncSession,
) -> uuid.UUID | None:
    """Confere que a carteira informada existe antes de gravar o vínculo."""
    if rep_id is None:
        return None
    exists = (
        await db.execute(
            select(Representative.id).where(Representative.id == rep_id).limit(1)
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Representante não encontrado.",
        )
    return rep_id


def sanitize_client_create_fields(data: dict, current_user: User) -> dict:
    """Espelho de `sanitize_client_update_fields` para o cadastro.

    Cadastro e edição seguem a mesma regra: representantes e vendedores podem
    escolher o perfil exibido no formulário, mas apenas `COMMERCIAL_ROLES`
    definem teto de desconto. O cliente-final nunca escolhe o próprio perfil.
    """
    if current_user.role not in COMMERCIAL_ROLES:
        data["max_discount"] = ClientCreate.model_fields["max_discount"].default
    if is_client_account(current_user):
        data["price_profile"] = ClientCreate.model_fields["price_profile"].default
    return data


async def _resolved_rep_id(
    data: dict,
    current_user: User,
    db: AsyncSession,
) -> uuid.UUID | None:
    """Carteira do cliente no cadastro — mesma regra do PATCH.

    Representante nunca escolhe: fica com a própria. Papel comercial
    (`COMMERCIAL_ROLES`) escolhe, e a carteira é validada contra a tabela. Os
    demais cadastram sem carteira e um papel comercial corrige depois pelo
    PATCH — antes as duas rotas discordavam e o vendedor interno gravava uma
    carteira que o sanitizador o impedia de mudar em seguida.
    """
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "O usuário representante não possui um registro "
                    "de representante associado."
                ),
            )
        return current_user.rep_id
    if current_user.role in COMMERCIAL_ROLES:
        return await _validated_rep_id(data.get("rep_id"), db)
    return None


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


async def _creator_names(
    db: AsyncSession,
    creator_ids: list[uuid.UUID | None],
) -> dict[uuid.UUID, str]:
    ids = [creator_id for creator_id in creator_ids if creator_id is not None]
    if not ids:
        return {}
    result = await db.execute(
        select(User.id, User.full_name).where(User.id.in_(ids))
    )
    return dict(result.all())


def _with_metadata(
    client: Client,
    status_map: dict[uuid.UUID, tuple[bool, bool]],
    creator_names: dict[uuid.UUID, str],
) -> ClientRead:
    has_user, user_validated = status_map.get(client.id, (False, False))
    # Objetos ainda não persistidos (usados também em testes/serviços internos)
    # não recebem o server_default antes do flush.
    if client.last_activity_at is None:
        client.last_activity_at = client.updated_at or client.created_at
    r = ClientRead.model_validate(client)
    return r.model_copy(
        update={
            "has_user": has_user,
            "user_validated": user_validated,
            "created_by_name": creator_names.get(client.created_by_user_id),
        }
    )


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
    current_user: User = Depends(require_directory_access),
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
    creator_names = (
        await _creator_names(db, [c.created_by_user_id for c in clients])
        if current_user.role not in (UserRole.representante, UserRole.cliente)
        and not is_client_account(current_user)
        else {}
    )
    return [_with_metadata(c, linked, creator_names) for c in clients]


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_roles(*_CREATE_CLIENT_ROLES)),
):
    data = payload.model_dump()
    duplicate_email = None
    if payload.email:
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
    # Só compara quando há documento: sem a guarda, `cpf_cnpj == None` viraria
    # `IS NULL` e o primeiro cadastro sem documento acusaria duplicidade de
    # todos os outros sem documento.
    if payload.cpf_cnpj:
        duplicate_document = (
            await db.execute(
                select(Client.id).where(Client.cpf_cnpj == payload.cpf_cnpj).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_document:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um cliente com este CPF/CNPJ.",
            )
    data = sanitize_client_create_fields(data, current_user)
    client = Client(**data, created_by_user_id=current_user.id)
    client.rep_id = await _resolved_rep_id(data, current_user, db)
    db.add(client)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_conflict_detail(error),
        )
    await db.refresh(client)
    return _with_metadata(
        client,
        {client.id: (False, False)},
        {current_user.id: current_user.full_name},
    )


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_directory_access),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    _rep_guard(client, current_user)
    linked = await _user_status(db, [client.id])
    creator_names = (
        await _creator_names(db, [client.created_by_user_id])
        if current_user.role not in (UserRole.representante, UserRole.cliente)
        and not is_client_account(current_user)
        else {}
    )
    return _with_metadata(client, linked, creator_names)


@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_directory_access),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    _rep_guard(client, current_user)
    update_data = sanitize_client_update_fields(
        payload.model_dump(exclude_unset=True), current_user
    )
    if "rep_id" in update_data:
        update_data["rep_id"] = await _validated_rep_id(update_data["rep_id"], db)
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
    new_document = update_data.get("cpf_cnpj")
    if new_document:
        duplicate_document = (
            await db.execute(
                select(Client.id).where(
                    Client.cpf_cnpj == new_document,
                    Client.id != client.id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_document:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um cliente com este CPF/CNPJ.",
            )
    for field, value in update_data.items():
        setattr(client, field, value)
    client.last_activity_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_conflict_detail(error),
        )
    await db.refresh(client)
    linked = await _user_status(db, [client.id])
    creator_names = (
        await _creator_names(db, [client.created_by_user_id])
        if current_user.role not in (UserRole.representante, UserRole.cliente)
        and not is_client_account(current_user)
        else {}
    )
    return _with_metadata(client, linked, creator_names)


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
    request: Request,
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

    linked_users = (await db.execute(
        select(User).where(User.linked_id == client_id, User.is_active.is_(True))
    )).scalars().all()
    for linked_user in linked_users:
        linked_user.is_active = False

    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="client",
        subject_id=client_id,
        action="personal_data_anonymized",
        request=request,
        legal_basis="LGPD Art. 18, IV",
        context={
            "disabled_accounts": len(linked_users),
            "self_service": False,
        },
    )
    await db.commit()
    logger.info("Anonimização admin: client_id=%s por user_id=%s", client_id, current_user.id)
