import re
import secrets
import uuid
import unicodedata
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import exists, func, or_, select, update

from app.api.deps import (
    get_db_session,
    get_current_user,
    require_platform_capability,
    require_roles,
)
from app.core.markets import PlatformPrincipal
from app.core.platform import lock_platform_admin_guard
from app.core.security import hash_password, validate_password_strength
from app.core.search import literal_contains_pattern
from app.models.user import User, UserRole
from app.models.client import Client
from app.models.representative import Representative
from app.models.refresh_token import RefreshToken
from app.models.market import (
    PLATFORM_CAPABILITIES,
    ProductMarket,
    UserMarket,
    UserPlatformPermission,
    VAT_APPROVED,
)
from app.schemas.auth import (
    UserRead,
    UserCreate,
    UserUpdate,
    UserPasswordReset,
    UserCreateResponse,
    UserMarketAccessInput,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])
_admin_only = require_roles(UserRole.admin)


class PlatformPermissionsUpdate(BaseModel):
    capabilities: set[Literal["platform_admin", "activate_market", "read_outbox"]]


async def _would_remove_last_platform_admin(
    db: AsyncSession, user_id: uuid.UUID
) -> bool:
    target_has_admin = (await db.execute(select(UserPlatformPermission.user_id).where(
        UserPlatformPermission.user_id == user_id,
        UserPlatformPermission.capability == "platform_admin",
        UserPlatformPermission.is_active.is_(True),
    ))).scalar_one_or_none()
    if target_has_admin is None:
        return False
    other = (await db.execute(
        select(UserPlatformPermission.user_id)
        .join(User, User.id == UserPlatformPermission.user_id)
        .where(
            UserPlatformPermission.capability == "platform_admin",
            UserPlatformPermission.is_active.is_(True),
            User.is_active.is_(True),
            UserPlatformPermission.user_id != user_id,
        ).limit(1)
    )).scalar_one_or_none()
    return other is None


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
    market_code: str | None = None,
) -> uuid.UUID | None:
    if role != UserRole.representante:
        return None
    if not rep_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Usuário representante precisa estar vinculado a um representante.",
        )
    exists = (
        await db.execute(
            select(Representative.id)
            .where(
                Representative.id == rep_id,
                *(
                    (Representative.market_code == market_code,)
                    if market_code is not None else ()
                ),
            )
            .execution_options(skip_market_scope=True)
            .limit(1)
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Representante vinculado não encontrado.",
        )
    return rep_id


async def _build_market_links(
    items: list[UserMarketAccessInput | dict], db: AsyncSession
) -> list[UserMarket]:
    items = [
        item if isinstance(item, UserMarketAccessInput) else UserMarketAccessInput.model_validate(item)
        for item in items
    ]
    codes = [item.market_code for item in items]
    if len(codes) != len(set(codes)):
        raise HTTPException(422, "Cada mercado pode aparecer apenas uma vez.")
    links: list[UserMarket] = []
    for item in items:
        direct_role = item.role in {
            UserRole.admin,
            UserRole.vendedor,
            UserRole.cadastros,
            UserRole.produtos,
            UserRole.executivo,
        }
        if item.role == UserRole.cliente:
            if item.linked_client_id is None or item.rep_id is not None:
                raise HTTPException(422, "Papel cliente exige somente linked_client_id.")
            valid = (await db.execute(select(Client.id).where(
                Client.id == item.linked_client_id,
                Client.market_code == item.market_code,
            ).execution_options(skip_market_scope=True))).scalar_one_or_none()
            if valid is None:
                raise HTTPException(422, "Cliente não pertence ao mercado informado.")
        elif item.role == UserRole.representante:
            if item.rep_id is None or item.linked_client_id is not None:
                raise HTTPException(422, "Papel representante exige somente rep_id.")
            valid = (await db.execute(select(Representative.id).where(
                Representative.id == item.rep_id,
                Representative.market_code == item.market_code,
            ).execution_options(skip_market_scope=True))).scalar_one_or_none()
            if valid is None:
                raise HTTPException(422, "Representante não pertence ao mercado informado.")
        elif direct_role:
            if item.linked_client_id is not None or item.rep_id is not None:
                raise HTTPException(422, "Este papel não aceita vínculo comercial.")
        links.append(UserMarket(
            market_code=item.market_code,
            role=item.role.value,
            status=item.status,
            linked_client_id=item.linked_client_id,
            rep_id=item.rep_id,
            can_view_dashboard=item.can_view_dashboard,
            can_approve_tax=item.can_approve_tax,
        ))
    return links


async def _replace_market_links(
    db: AsyncSession, user: User, desired: list[UserMarket]
) -> None:
    """Reconcilia vínculos sem reinserir uma PK `(user_id, market_code)` existente."""
    existing = {link.market_code: link for link in user.allowed_market_links}
    desired_codes = {link.market_code for link in desired}
    for code, current in existing.items():
        if code not in desired_codes:
            await db.delete(current)
            user.allowed_market_links.remove(current)
    for incoming in desired:
        current = existing.get(incoming.market_code)
        if current is None:
            user.allowed_market_links.append(incoming)
            continue
        for field in (
            "role", "status", "linked_client_id", "rep_id",
            "can_view_dashboard", "can_approve_tax",
        ):
            setattr(current, field, getattr(incoming, field))


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
    market: Literal["BR", "EU"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    filters = []
    if market:
        filters.append(exists().where(UserMarket.user_id == User.id, UserMarket.market_code == market))
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
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    # BUG-03 (Bloco 88): mesma política de complexidade do change-password
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    if body.role == UserRole.cliente:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    if body.username:
        taken = await db.execute(
            select(User.id).where(User.username == body.username).limit(1)
        )
        if taken.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Usuário já cadastrado.")
    links = await _build_market_links(body.market_accesses, db)
    home_link = None
    if links:
        if body.home_market not in {link.market_code for link in links}:
            raise HTTPException(422, "home_market deve existir em market_accesses.")
        home_link = next(link for link in links if link.market_code == body.home_market)
        if body.role.value != home_link.role:
            raise HTTPException(422, "role deve corresponder ao papel do mercado principal.")
        if body.rep_id != home_link.rep_id:
            raise HTTPException(422, "rep_id deve corresponder ao vínculo do mercado principal.")
    elif body.role != UserRole.vendedor or body.rep_id is not None:
        raise HTTPException(
            422,
            "Identidade sem mercado usa o papel técnico vendedor e não aceita vínculo comercial.",
        )
    user = User(
        email=normalized_email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role if home_link else UserRole.vendedor,
        rep_id=home_link.rep_id if home_link else None,
        linked_id=home_link.linked_client_id if home_link else None,
        # Coluna legada ainda é NOT NULL. Sem user_markets ela não concede BR.
        home_market=body.home_market if home_link else "BR",
    )
    user.allowed_market_links = links
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "E-mail, usuário ou representante já vinculado a outra conta.",
        )
    await db.refresh(user)
    return user


@router.put("/{user_id}/platform-permissions")
async def replace_platform_permissions(
    user_id: uuid.UUID,
    body: PlatformPermissionsUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuário não encontrado.")
    await lock_platform_admin_guard(db)
    if (
        "platform_admin" not in body.capabilities
        and await _would_remove_last_platform_admin(db, user_id)
    ):
        raise HTTPException(409, "A plataforma precisa manter ao menos um administrador ativo.")
    existing = list((await db.execute(select(UserPlatformPermission).where(
        UserPlatformPermission.user_id == user_id
    ))).scalars().all())
    by_capability = {item.capability: item for item in existing}
    for capability in PLATFORM_CAPABILITIES:
        permission = by_capability.get(capability)
        should_be_active = capability in body.capabilities
        if permission is None and should_be_active:
            db.add(UserPlatformPermission(
                user_id=user_id, capability=capability, is_active=True
            ))
        elif permission is not None:
            permission.is_active = should_be_active
    await db.execute(update(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.scope == "platform",
        RefreshToken.revoked.is_(False),
    ).values(revoked=True, revoked_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"user_id": user_id, "capabilities": sorted(body.capabilities)}


@router.get("/{user_id}/platform-permissions")
async def get_platform_permissions(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    if await db.get(User, user_id) is None:
        raise HTTPException(404, "Usuário não encontrado.")
    capabilities = (await db.execute(select(
        UserPlatformPermission.capability
    ).where(
        UserPlatformPermission.user_id == user_id,
        UserPlatformPermission.is_active.is_(True),
    ))).scalars().all()
    return {"user_id": user_id, "capabilities": sorted(capabilities)}


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
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
    market_accesses = changes.pop("market_accesses", None)
    market_access_changed = market_accesses is not None
    legacy_identity_synced = False
    if market_accesses is not None:
        links = await _build_market_links(market_accesses, db)
        if links:
            target_home = changes.get("home_market", user.home_market)
            if target_home not in {link.market_code for link in links}:
                raise HTTPException(422, "home_market deve existir em market_accesses.")
            home_link = next(link for link in links if link.market_code == target_home)
            submitted_role = changes.get("role")
            if submitted_role is not None and submitted_role.value != home_link.role:
                raise HTTPException(422, "role deve corresponder ao papel do mercado principal.")
            submitted_rep_id = changes.get("rep_id")
            if "rep_id" in changes and submitted_rep_id != home_link.rep_id:
                raise HTTPException(422, "rep_id deve corresponder ao vínculo do mercado principal.")
            changes["role"] = UserRole(home_link.role)
            changes["rep_id"] = home_link.rep_id
            changes["linked_id"] = home_link.linked_client_id
            changes["can_view_dashboard"] = home_link.can_view_dashboard
        else:
            # Espelhos legados neutros. Sem linha em user_markets não há acesso
            # comercial, mesmo com home_market='BR' na coluna NOT NULL antiga.
            changes["home_market"] = "BR"
            changes["role"] = UserRole.vendedor
            changes["rep_id"] = None
            changes["linked_id"] = None
            changes["can_view_dashboard"] = False
        await _replace_market_links(db, user, links)
        legacy_identity_synced = True
    elif "home_market" in changes:
        if changes["home_market"] not in user.allowed_markets:
            raise HTTPException(422, "home_market deve existir nos vínculos atuais.")
        home_link = next(
            link for link in user.allowed_market_links
            if link.market_code == changes["home_market"]
        )
        if home_link.role is None:
            raise HTTPException(422, "O mercado principal precisa ter papel definido.")
        changes["role"] = UserRole(home_link.role)
        changes["rep_id"] = home_link.rep_id
        changes["linked_id"] = home_link.linked_client_id
        changes["can_view_dashboard"] = home_link.can_view_dashboard
        legacy_identity_synced = True
    elif any(field in changes for field in ("role", "rep_id", "can_view_dashboard")):
        raise HTTPException(
            422,
            "Alterações de papel e vínculo devem incluir market_accesses.",
        )
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
    new_username = changes.get("username")
    if new_username and new_username != user.username:
        duplicate_username = (
            await db.execute(
                select(User.id)
                .where(User.username == new_username, User.id != user.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_username:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Usuário já cadastrado.",
            )
    target_role = changes.get("role", user.role)
    target_rep_id = changes.get("rep_id", user.rep_id)
    target_home_market = changes.get("home_market", user.home_market)
    changes["rep_id"] = await _validated_rep_assignment(
        target_role,
        target_rep_id,
        db,
        target_home_market,
    )
    if legacy_identity_synced:
        # Os campos globais permanecem apenas como espelho compatível do
        # vínculo do mercado principal; a autoridade está em user_markets.
        pass
    elif target_role == UserRole.representante:
        changes["linked_id"] = changes["rep_id"]
    elif target_role == UserRole.cliente:
        if user.role == UserRole.representante or user.linked_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Vincule a conta a um cliente pelo fluxo de cadastro.",
            )
        changes["linked_id"] = user.linked_id
    elif user.role == UserRole.representante:
        changes["linked_id"] = None
    elif target_role == UserRole.vendedor:
        changes["linked_id"] = user.linked_id
    else:
        changes["linked_id"] = None
    identity_security_changed = any(
        field in changes and changes[field] != getattr(user, field)
        for field in ("username", "is_active")
    )
    commercial_security_changed = market_access_changed or (
        "home_market" in changes and changes["home_market"] != user.home_market
    )
    if changes.get("is_active") is False:
        await lock_platform_admin_guard(db)
        if await _would_remove_last_platform_admin(db, user.id):
            raise HTTPException(409, "A plataforma precisa manter ao menos um administrador ativo.")
    for field, value in changes.items():
        setattr(user, field, value)
    if identity_security_changed:
        user.auth_version += 1
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
    elif commercial_security_changed:
        # Papéis e vínculos são relidos de user_markets em toda requisição e
        # refresh comercial. Revogar somente as famílias comerciais mantém uma
        # sessão de plataforma independente ativa durante a administração.
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.scope == "market",
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "E-mail, usuário ou representante já vinculado a outra conta.",
        )
    await db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    body: UserPasswordReset,
    db: AsyncSession = Depends(get_db_session),
    _: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    # BUG-03 (Bloco 88): reset administrativo também exige senha forte
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
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
    platform: PlatformPrincipal = Depends(require_platform_capability("platform_admin")),
):
    if user_id == platform.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não é possível excluir o próprio usuário.")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    approved_vat = (await db.execute(
        select(ProductMarket.product_id).where(
            ProductMarket.approved_by_user_id == user_id,
            ProductMarket.vat_status == VAT_APPROVED,
        ).limit(1)
    )).scalar_one_or_none()
    if approved_vat is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A conta possui aprovações fiscais ativas e não pode ser excluída.",
        )
    await lock_platform_admin_guard(db)
    if await _would_remove_last_platform_admin(db, user_id):
        raise HTTPException(409, "A plataforma precisa manter ao menos um administrador ativo.")
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

    linked_result = await db.execute(
        select(UserMarket.user_id).where(
            UserMarket.market_code == client.market_code,
            UserMarket.role == UserRole.cliente.value,
            UserMarket.linked_client_id == client_id,
        ).limit(1)
    )
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
        home_market=client.market_code,
    )
    user.allowed_market_links = [UserMarket(
        market_code=client.market_code,
        role=UserRole.cliente.value,
        status="active",
        linked_client_id=client.id,
    )]
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
        select(UserMarket.user_id).where(
            UserMarket.market_code == rep.market_code,
            UserMarket.role == UserRole.representante.value,
            UserMarket.rep_id == rep_id,
        ).limit(1)
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
        home_market=rep.market_code,
    )
    user.allowed_market_links = [UserMarket(
        market_code=rep.market_code,
        role=UserRole.representante.value,
        status="active",
        rep_id=rep.id,
    )]
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
