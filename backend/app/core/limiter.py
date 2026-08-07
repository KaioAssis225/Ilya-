import hashlib

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import decode_access_token


_storage_options = (
    {}
    if settings.RATE_LIMIT_STORAGE_URI.startswith("memory://")
    else {
        "socket_connect_timeout": settings.RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        "socket_timeout": settings.RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        "health_check_interval": 30,
    }
)

def rate_limit_key(request: Request) -> str:
    """Compartilha limites por usuário sem penalizar todos atrás do mesmo NAT."""
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and token:
        payload = decode_access_token(token)
        subject = payload.get("sub") if payload else None
        if subject:
            return f"user:{subject}"
    return f"ip:{get_remote_address(request)}"


def refresh_rate_limit_key(request: Request) -> str:
    """Chave por sessão para a renovação de token.

    O /auth/refresh não manda Authorization — só o cookie HttpOnly — então a
    chave padrão cairia no IP e uma equipe inteira atrás do mesmo NAT (feira,
    showroom, escritório) dividiria o mesmo balde: bastariam poucas renovações
    simultâneas para derrubar a sessão dos demais. O hash do próprio cookie
    isola cada sessão, que é o alvo real do limite. Sem cookie, mantém o IP.
    """
    cookie = request.cookies.get("ilya_refresh")
    if cookie:
        return f"session:{hashlib.sha256(cookie.encode()).hexdigest()[:32]}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    storage_options=_storage_options,
    headers_enabled=True,
)
