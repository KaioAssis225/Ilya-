"""Contenção progressiva de login sem permitir bloqueio global dirigido."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from slowapi.util import get_remote_address
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.login_attempt_state import LoginAttemptState


logger = logging.getLogger("ilya.auth")


@dataclass(frozen=True)
class LoginAttemptKey:
    identifier: str
    origin: str


def _fingerprint(purpose: str, value: str) -> str:
    key = hashlib.sha256(
        f"{settings.SECRET_KEY}:{settings.PASSWORD_PEPPER}".encode("utf-8")
    ).digest()
    return hmac.new(key, f"{purpose}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def login_attempt_key(request: Request, normalized_identifier: str) -> LoginAttemptKey:
    # O Uvicorn só aplica X-Forwarded-For quando o peer pertence à allowlist.
    # Não lemos o cabeçalho diretamente: request.client é a fronteira validada.
    origin = get_remote_address(request) or "unknown"
    return LoginAttemptKey(
        identifier=_fingerprint("login-identifier", normalized_identifier),
        origin=_fingerprint("login-origin", origin),
    )


async def enforce_login_cooldown(
    db: AsyncSession,
    key: LoginAttemptKey,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(timezone.utc)
    state = (await db.execute(
        select(LoginAttemptState).where(
            LoginAttemptState.identifier_fingerprint == key.identifier,
            LoginAttemptState.origin_fingerprint == key.origin,
        )
    )).scalar_one_or_none()
    if state is None or state.cooldown_until is None:
        return
    cooldown_until = state.cooldown_until
    if cooldown_until.tzinfo is None:
        cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
    if cooldown_until <= current_time:
        return
    retry_after = max(1, int((cooldown_until - current_time).total_seconds()))
    logger.warning(
        "Login contido por origem+identificador: identifier_fp=%s origin_fp=%s retry_after=%s",
        key.identifier[:12], key.origin[:12], retry_after,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Muitas tentativas. Aguarde antes de tentar novamente.",
        headers={"Retry-After": str(retry_after)},
    )


async def record_login_failure(
    db: AsyncSession,
    key: LoginAttemptKey,
    *,
    now: datetime | None = None,
) -> tuple[int, datetime | None, int]:
    current_time = now or datetime.now(timezone.utc)
    window_cutoff = current_time - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)
    expired = LoginAttemptState.last_failed_at < window_cutoff
    next_count = case((expired, 1), else_=LoginAttemptState.failure_count + 1)
    active_count = LoginAttemptState.failure_count + 1
    next_cooldown = case(
        (expired, None),
        (active_count >= 15, current_time + timedelta(minutes=5)),
        (active_count >= 10, current_time + timedelta(minutes=2)),
        (active_count >= 5, current_time + timedelta(seconds=30)),
        else_=None,
    )
    statement = insert(LoginAttemptState).values(
        identifier_fingerprint=key.identifier,
        origin_fingerprint=key.origin,
        failure_count=1,
        window_started_at=current_time,
        last_failed_at=current_time,
        cooldown_until=None,
    ).on_conflict_do_update(
        index_elements=["identifier_fingerprint", "origin_fingerprint"],
        set_={
            "failure_count": next_count,
            "window_started_at": case(
                (expired, current_time), else_=LoginAttemptState.window_started_at
            ),
            "last_failed_at": current_time,
            "cooldown_until": next_cooldown,
        },
    ).returning(
        LoginAttemptState.failure_count,
        LoginAttemptState.cooldown_until,
    )
    row = (await db.execute(statement)).one()
    directed_total = int((await db.execute(
        select(func.coalesce(func.sum(LoginAttemptState.failure_count), 0)).where(
            LoginAttemptState.identifier_fingerprint == key.identifier,
            LoginAttemptState.last_failed_at >= window_cutoff,
        )
    )).scalar_one())
    if directed_total >= settings.LOGIN_DIRECTED_ALERT_THRESHOLD:
        logger.warning(
            "Falhas dirigidas distribuídas: identifier_fp=%s failures=%s",
            key.identifier[:12], directed_total,
        )
    return row.failure_count, row.cooldown_until, directed_total


async def clear_login_failure(db: AsyncSession, key: LoginAttemptKey) -> None:
    await db.execute(delete(LoginAttemptState).where(
        LoginAttemptState.identifier_fingerprint == key.identifier,
        LoginAttemptState.origin_fingerprint == key.origin,
    ))


async def cleanup_login_attempt_states(db: AsyncSession, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(delete(LoginAttemptState).where(
        LoginAttemptState.last_failed_at < cutoff,
    ))
    await db.commit()
    return result.rowcount or 0
