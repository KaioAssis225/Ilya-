import logging
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, delete, update

from app.api.deps import get_db_session, get_authenticated_user, get_current_user, is_client_account
from app.core.limiter import limiter
from app.core.security import (
    verify_password,
    dummy_verify,
    hash_password,
    validate_password_strength,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from decimal import Decimal

from app.core.config import settings
from app.models.user import User, UserRole
from app.models.client import Client, anonymize_client_fields
from app.models.representative import Representative
from app.models.refresh_token import RefreshToken
from app.models.notification import Notification
from app.models.order import Order
from app.models.signature_invitation import SignatureInvitation
from app.schemas.auth import (
    LoginRequest,
    AccessTokenResponse,
    UserRead,
    ChangePasswordRequest,
    ReauthenticationRequest,
)

logger = logging.getLogger("ilya.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_NAME = "ilya_refresh"
_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_TTL_DAYS * 86400
_LOGIN_LOCK_THRESHOLD = 5
_LOGIN_LOCK_MINUTES = 15


async def _revoke_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> None:
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False),
    )
    await db.execute(
        stmt.values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        # SameSite=None é obrigatório para o cookie ser enviado em requisições
        # cross-origin (frontend e backend em domínios diferentes, ex.: Vercel +
        # Railway); exige Secure=True (só funciona em HTTPS). Em dev local, o
        # front chama a API via proxy same-origin, então Lax basta e evita
        # exigir HTTPS na máquina do dev.
        samesite="none" if not settings.DEBUG else "lax",
        secure=not settings.DEBUG,
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/api/v1/auth",
        samesite="none" if not settings.DEBUG else "lax",
        secure=not settings.DEBUG,
    )


@router.post("/login", response_model=AccessTokenResponse)
@limiter.limit("5/15minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(User).where(
            or_(User.email == payload.identifier, User.username == payload.identifier)
        )
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        dummy_verify()
        logger.warning(
            "Falha de login: request_id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        dummy_verify()
        logger.warning("Login bloqueado temporariamente: user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _LOGIN_LOCK_THRESHOLD:
            user.locked_until = now + timedelta(minutes=_LOGIN_LOCK_MINUTES)
            user.failed_login_attempts = 0
        await db.commit()
        logger.warning(
            "Falha de login: request_id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    logger.info("Login: user_id=%s role=%s", user.id, user.role.value)

    access_token = create_access_token(user.id, user.role.value, user.auth_version)
    raw_refresh = generate_refresh_token()
    family_id = uuid.uuid4()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=refresh_token_expiry(),
        family_id=family_id,
    ))
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return AccessTokenResponse(access_token=access_token)


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("5/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
):
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido ou expirado.",
    )
    if not refresh_token:
        raise invalid_exc

    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
        ).with_for_update()
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise invalid_exc

    if stored.revoked or stored.used_at is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id)
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
        logger.warning(
            "Reutilização de refresh token detectada; família revogada: user_id=%s family_id=%s",
            stored.user_id,
            stored.family_id,
        )
        raise invalid_exc

    now = datetime.now(timezone.utc)
    if stored.expires_at.replace(tzinfo=timezone.utc) < now:
        stored.revoked = True
        stored.revoked_at = now
        await db.commit()
        raise invalid_exc

    user_result = await db.execute(
        select(User).where(User.id == stored.user_id, User.is_active.is_(True))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise invalid_exc

    stored.revoked = True
    stored.used_at = now
    stored.revoked_at = now
    new_refresh_raw = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_raw),
        expires_at=refresh_token_expiry(),
        family_id=stored.family_id,
        parent_id=stored.id,
    ))
    await db.commit()

    _set_refresh_cookie(response, new_refresh_raw)
    return AccessTokenResponse(
        access_token=create_access_token(user.id, user.role.value, user.auth_version)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
):
    if refresh_token:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        )
        stored = result.scalar_one_or_none()
        if stored:
            stored.revoked = True
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Logout: token revogado")
    _clear_refresh_cookie(response)


async def _resolve_max_discount(db: AsyncSession, user: User) -> Decimal:
    """Bloco 69: teto de desconto por item, dinamico conforme a role logada."""
    if user.role == UserRole.representante and user.rep_id:
        rep = (await db.execute(select(Representative).where(Representative.id == user.rep_id))).scalar_one_or_none()
        return rep.max_discount if rep else Decimal("0.00")
    if is_client_account(user) and user.linked_id:
        client = (await db.execute(select(Client).where(Client.id == user.linked_id))).scalar_one_or_none()
        return client.max_discount if client else Decimal("0.00")
    return Decimal("100.00")


@router.get("/me", response_model=UserRead)
async def me(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    max_discount = await _resolve_max_discount(db, current_user)
    data = UserRead.model_validate(current_user).model_dump()
    data["max_discount"] = max_discount
    return data


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    response: Response,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    if not user.must_change_password:
        if not body.current_password or not verify_password(body.current_password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha atual incorreta.")
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    user.auth_version += 1
    await _revoke_user_sessions(db, user.id)
    await db.commit()
    _clear_refresh_cookie(response)
    logger.info("Senha alterada e sessões revogadas: user_id=%s", user.id)


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
):
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at >= now_naive,
            )
            .order_by(RefreshToken.created_at.desc())
        )
    ).scalars().all()
    current_hash = hash_refresh_token(refresh_token) if refresh_token else None
    return [
        {
            "id": str(session.id),
            "criada_em": session.created_at,
            "expira_em": session.expires_at,
            "sessao_atual": session.token_hash == current_hash,
        }
        for session in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    session = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada.")
    session.revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one()
    user.auth_version += 1
    await _revoke_user_sessions(db, user.id)
    await db.commit()
    _clear_refresh_cookie(response)
    logger.info("Todas as sessões encerradas: user_id=%s", user.id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/minute")
async def delete_my_account(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Bloco 93: exclusão da própria conta pelo titular.

    Remove o usuário fisicamente — refresh tokens caem por CASCADE (revogação),
    order_history.user_id vira NULL (trilha preservada) e as notificações são
    apagadas antes (FK sem ondelete). O registro comercial de Cliente/Representante
    vinculado NÃO é excluído; para dados pessoais há o fluxo de anonimização."""
    if current_user.role == UserRole.admin:
        others = await db.execute(
            select(User).where(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.id != current_user.id,
            )
        )
        if not others.scalars().first():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Não é possível excluir o único administrador ativo do sistema.",
            )

    await db.execute(delete(Notification).where(Notification.user_id == current_user.id))
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    await db.delete(user)
    await db.commit()
    logger.info("Conta excluída pelo titular: user_id=%s", current_user.id)
    _clear_refresh_cookie(response)


def _order_personal_data(order: Order) -> dict:
    """Serializa dados do pedido sem devolver as imagens de assinatura."""
    return {
        "id": str(order.id),
        "codigo": order.code,
        "orcamento": order.orc_id,
        "valor_total": order.total_value,
        "ipi_total": order.total_ipi,
        "valor_com_ipi": order.total_with_ipi,
        "observacoes": order.notes,
        "finalizado": order.is_finalized,
        "assinatura_representante_registrada": order.rep_signed,
        "assinatura_cliente_registrada": order.client_signed,
        "criado_em": order.created_at,
        "atualizado_em": order.updated_at,
        "itens": [
            {
                "codigo_produto": item.product_code,
                "descricao": item.description,
                "quantidade": item.qty,
                "valor_unitario": item.unit_price,
                "desconto": item.discount,
                "ipi": item.ipi_rate,
                "opcionais": item.opt_categories,
            }
            for item in order.items
        ],
    }


@router.get("/my-data")
async def my_data(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """ACT-01 / ACT-02: retorna todos os dados pessoais do titular (Art. 18, I e II)."""
    payload: dict = {
        "usuario": {
            "id": str(current_user.id),
            "nome": current_user.full_name,
            "email": current_user.email,
            "username": current_user.username,
            "role": current_user.role.value,
            "ativo": current_user.is_active,
            "criado_em": current_user.created_at,
            "atualizado_em": current_user.updated_at,
        },
        "dados_cliente": None,
        "dados_representante": None,
        "pedidos": [],
        "notificacoes": [],
        "sessoes": [],
    }
    if current_user.linked_id and is_client_account(current_user):
        client = (await db.execute(select(Client).where(Client.id == current_user.linked_id))).scalar_one_or_none()
        if client:
            payload["dados_cliente"] = {
                "id": str(client.id),
                "nome": client.name,
                "telefone": client.phone,
                "email": client.email,
                "cep": client.cep,
                "numero": client.numero,
                "endereco": client.address,
                "cidade": client.city,
                "estado": client.state,
            }
            orders = (
                await db.execute(
                    select(Order)
                    .where(Order.client_id == client.id)
                    .order_by(Order.created_at.desc())
                )
            ).scalars().all()
            payload["pedidos"] = [_order_personal_data(order) for order in orders]
    elif current_user.role == UserRole.representante and current_user.rep_id:
        representative = (
            await db.execute(
                select(Representative).where(Representative.id == current_user.rep_id)
            )
        ).scalar_one_or_none()
        if representative:
            payload["dados_representante"] = {
                "id": str(representative.id),
                "nome": representative.name,
                "telefone": representative.phone,
                "email": representative.email,
                "cep": representative.cep,
                "numero": representative.numero,
                "endereco": representative.address,
                "cidade": representative.city,
                "estado": representative.state,
            }
            orders = (
                await db.execute(
                    select(Order)
                    .where(Order.rep_id == representative.id)
                    .order_by(Order.created_at.desc())
                )
            ).scalars().all()
            payload["pedidos"] = [_order_personal_data(order) for order in orders]

    notifications = (
        await db.execute(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
        )
    ).scalars().all()
    payload["notificacoes"] = [
        {
            "id": str(notification.id),
            "mensagem": notification.message,
            "lida": notification.is_read,
            "criada_em": notification.created_at,
        }
        for notification in notifications
    ]

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    sessions = (
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at >= now_naive,
            )
            .order_by(RefreshToken.created_at.desc())
        )
    ).scalars().all()
    payload["sessoes"] = [
        {
            "id": str(session.id),
            "criada_em": session.created_at,
            "expira_em": session.expires_at,
        }
        for session in sessions
    ]
    return payload


@router.post("/my-data/export")
@limiter.limit("3/hour")
async def my_data_export(
    request: Request,
    body: ReauthenticationRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """ACT-02: exportação portável dos dados pessoais em JSON (Art. 18, V)."""
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha incorreta.")
    data = await my_data(db=db, current_user=current_user)
    import json
    content = json.dumps(jsonable_encoder(data), ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=\"meus-dados-ilya.json\"",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.post("/anonymize", status_code=status.HTTP_204_NO_CONTENT)
async def anonymize_my_data(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """ACT-03: anonimiza os dados PII do titular e desativa a conta (Art. 18, IV e VI)."""
    if not is_client_account(current_user) or not current_user.linked_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operação disponível apenas para usuários clientes.")

    client = (await db.execute(select(Client).where(Client.id == current_user.linked_id))).scalar_one_or_none()
    if client:
        anonymize_client_fields(client)

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    user.email = f"anonimizado_{user.id}@excluido.ilya"
    user.username = None
    user.full_name = "USUÁRIO ANONIMIZADO"
    user.hashed_password = hash_password(generate_refresh_token())
    user.is_active = False
    user.auth_version += 1
    await _revoke_user_sessions(db, user.id)
    await db.execute(delete(Notification).where(Notification.user_id == user.id))
    await db.execute(
        update(SignatureInvitation)
        .where(
            SignatureInvitation.client_id == current_user.linked_id,
            SignatureInvitation.consumed_at.is_(None),
            SignatureInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )

    await db.commit()
    logger.info("Anonimização solicitada: user_id=%s client_id=%s", current_user.id, current_user.linked_id)
    _clear_refresh_cookie(response)
