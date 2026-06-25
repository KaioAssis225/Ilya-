from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.core.security import (
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    decode_access_token,
)
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest, UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh)

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=refresh_token_expiry(),
    ))
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db_session),
):
    from datetime import datetime
    token_hash = hash_refresh_token(payload.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
    )
    stored = result.scalar_one_or_none()

    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido ou expirado.",
    )
    if not stored:
        raise invalid_exc

    now = datetime.now(timezone.utc)
    if stored.expires_at.replace(tzinfo=timezone.utc) < now:
        stored.revoked = True
        await db.commit()
        raise invalid_exc

    user_result = await db.execute(select(User).where(User.id == stored.user_id, User.is_active.is_(True)))
    user = user_result.scalar_one_or_none()
    if not user:
        raise invalid_exc

    # Rotação: revoga token antigo, emite par novo
    stored.revoked = True
    new_refresh_raw = generate_refresh_token()
    new_hash = hash_refresh_token(new_refresh_raw)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=refresh_token_expiry(),
    ))
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=new_refresh_raw,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db_session),
):
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        await db.commit()


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
