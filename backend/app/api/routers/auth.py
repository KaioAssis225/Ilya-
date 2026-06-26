import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.core.limiter import limiter
from app.core.security import (
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.core.config import settings
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import LoginRequest, AccessTokenResponse, UserRead

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
        secure=not settings.DEBUG,  # True em produção (HTTPS), False em dev
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
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Falha de login: ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
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
async def refresh(
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
async def me(current_user: User = Depends(get_current_user)):
    return current_user
