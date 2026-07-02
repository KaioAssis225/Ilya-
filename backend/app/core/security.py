import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import settings

# OWASP recommendation: time_cost>=3, memory_cost>=64MB, parallelism>=4
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

ALGORITHM = "HS256"


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _hasher.hash(plain + settings.PASSWORD_PEPPER)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain + settings.PASSWORD_PEPPER)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Pré-computado na inicialização para uniformizar o tempo de resposta do login
# quando o usuário não existe (CWE-204 timing side-channel mitigation).
_DUMMY_HASH: str = _hasher.hash("ilya_sentinel_dummy_2026")


def dummy_verify() -> None:
    """Queima tempo Argon2 equivalente quando usuário não é encontrado no login."""
    try:
        _hasher.verify(_DUMMY_HASH, "nonexistent")
    except Exception:
        pass


# ── JWT Access Token ──────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ── Refresh Token ─────────────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    # Coluna no DB é TIMESTAMP WITHOUT TIME ZONE — armazena UTC naive
    return (datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)).replace(tzinfo=None)


# ── Sign Token (10-min, for contract signing) ─────────────────────────────────
# Janela curta reduz o risco de replay caso o link seja interceptado (V-S3).
# A assinatura em si é single-use: sign_with_token rejeita (409) se já assinado.
SIGN_TOKEN_TTL_MINUTES = 10


def create_sign_token(order_id: str, client_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=SIGN_TOKEN_TTL_MINUTES)
    payload = {"order_id": order_id, "client_id": client_id, "exp": expire, "type": "sign"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_sign_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], leeway=timedelta(seconds=30))
        if payload.get("type") != "sign":
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
