import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.api.deps import get_db_session, get_authenticated_user, get_current_user
from app.core.limiter import limiter
from app.core.security import (
    verify_password,
    dummy_verify,
    hash_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.client import Client
from app.models.refresh_token import RefreshToken
from app.schemas.auth import LoginRequest, AccessTokenResponse, UserRead, ChangePasswordRequest

logger = logging.getLogger("ilya.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_NAME = "ilya_refresh"
_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_TTL_DAYS * 86400


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=not settings.DEBUG,
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_NAME, path="/api/v1/auth")


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
            or_(User.email == payload.identifier, User.username == payload.identifier),
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        dummy_verify()
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Falha de login: ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    if not verify_password(payload.password, user.hashed_password):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Falha de login: ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
        )

    logger.info("Login: user_id=%s role=%s", user.id, user.role.value)

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=refresh_token_expiry(),
    ))
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return AccessTokenResponse(access_token=access_token)


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("20/minute")
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
            RefreshToken.revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise invalid_exc

    now = datetime.now(timezone.utc)
    if stored.expires_at.replace(tzinfo=timezone.utc) < now:
        stored.revoked = True
        await db.commit()
        raise invalid_exc

    user_result = await db.execute(
        select(User).where(User.id == stored.user_id, User.is_active.is_(True))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise invalid_exc

    stored.revoked = True
    new_refresh_raw = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh_raw),
        expires_at=refresh_token_expiry(),
    ))
    await db.commit()

    _set_refresh_cookie(response, new_refresh_raw)
    return AccessTokenResponse(access_token=create_access_token(user.id, user.role.value))


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
            await db.commit()
            logger.info("Logout: token revogado")
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_authenticated_user)):
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    if len(body.new_password) < 8:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A senha deve ter pelo menos 8 caracteres.")
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()


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
        },
        "dados_cliente": None,
    }
    if current_user.linked_id and current_user.role == UserRole.vendedor:
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
    return payload


@router.get("/my-data/export")
async def my_data_export(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_authenticated_user),
):
    """ACT-02: exportação portável dos dados pessoais em JSON (Art. 18, V)."""
    data = await my_data(db=db, current_user=current_user)
    import json
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"meus-dados-ilya.json\""},
    )


@router.post("/anonymize", status_code=status.HTTP_204_NO_CONTENT)
async def anonymize_my_data(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """ACT-03: anonimiza os dados PII do titular e desativa a conta (Art. 18, IV e VI)."""
    if current_user.role != UserRole.vendedor or not current_user.linked_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operação disponível apenas para usuários clientes.")

    client = (await db.execute(select(Client).where(Client.id == current_user.linked_id))).scalar_one_or_none()
    if client:
        client.name = "CLIENTE ANONIMIZADO"
        client.phone = "(00) 00000-0000"
        client.email = f"anonimizado_{client.id}@excluido.ilya"
        client.cep = "00000-000"
        client.numero = None
        client.address = "Endereço Excluído, 00"
        client.city = "—"
        client.state = "EX"

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    user.is_active = False

    await db.commit()
    logger.info("Anonimização solicitada: user_id=%s client_id=%s", current_user.id, current_user.linked_id)
    _clear_refresh_cookie(response)
