"""Emissão da autorização (handoff) para o Estoque Brasil — ES256, 60 s.

Contrato (PEDIDO-AO-MAESTRO-DO-ILYA.md, seção 3):
- header: alg=ES256, typ=JWT, kid;
- claims: iss="ilya", aud="ilya-estoque", typ="stock-handoff", sub (users.id),
  ver (users.auth_version), iat, exp=iat+60, jti (uuid4);
- NADA além disso: sem e-mail, nome, papel ou telefone.

A chave privada vem só de variável de ambiente. Nada aqui grava, registra ou
devolve a chave; falhas de configuração viram "não configurado" (503) sem
vazar o conteúdo.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger("ilya.stock_handoff")

ISSUER = "ilya"
AUDIENCE = "ilya-estoque"
TOKEN_TYPE = "stock-handoff"
ALGORITHM = "ES256"
LIFETIME_SECONDS = 60


@dataclass(frozen=True)
class HandoffSigner:
    private_key: ec.EllipticCurvePrivateKey
    kid: str
    origin: str


def _normalize_origin(raw: str) -> str | None:
    """Aceita só `scheme://host[:porta]`, sem caminho; http apenas em localhost."""
    value = (raw or "").strip()
    parts = urlsplit(value)
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        return None
    if not parts.hostname:
        return None
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        return None
    return f"{parts.scheme}://{parts.netloc}"


@lru_cache(maxsize=4)
def _load_key(pem: str) -> ec.EllipticCurvePrivateKey | None:
    # Railway costuma entregar a quebra de linha do PEM como "\n" literal.
    text = pem.replace("\\n", "\n").strip()
    try:
        key = serialization.load_pem_private_key(text.encode(), password=None)
    except (ValueError, TypeError):
        logger.error("STOCK_HANDOFF_PRIVATE_KEY inválida (não é um PEM de chave privada).")
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        logger.error("STOCK_HANDOFF_PRIVATE_KEY precisa ser EC P-256 (ES256).")
        return None
    return key


def get_signer() -> HandoffSigner | None:
    """Assinador pronto, ou None se faltar chave, kid ou origem válidos."""
    pem = settings.STOCK_HANDOFF_PRIVATE_KEY
    kid = settings.STOCK_HANDOFF_KID.strip()
    origin = _normalize_origin(settings.STOCK_APP_ORIGIN)
    if not pem.strip() or not kid or origin is None:
        return None
    key = _load_key(pem)
    if key is None:
        return None
    return HandoffSigner(private_key=key, kid=kid, origin=origin)


def stock_handoff_configured() -> bool:
    return get_signer() is not None


def issue_assertion(user: User, signer: HandoffSigner) -> tuple[str, str]:
    """Devolve `(jwt, jti)`. O `jti` pode ir para a auditoria; o JWT, nunca."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "typ": TOKEN_TYPE,
        "sub": str(user.id),
        "ver": user.auth_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=LIFETIME_SECONDS)).timestamp()),
        "jti": jti,
    }
    token = jwt.encode(
        claims,
        signer.private_key,
        algorithm=ALGORITHM,
        headers={"kid": signer.kid, "typ": "JWT"},
    )
    return token, jti
