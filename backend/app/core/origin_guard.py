import re
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.core.config import settings


def _referer_origin(referer: str) -> str | None:
    parts = urlsplit(referer)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def is_trusted_origin(origin: str) -> bool:
    """Compara a origem contra a allowlist do CORS: lista exata (`in`, sem
    substring) OU a regex de preview da Vercel inteira (`re.fullmatch`).
    Um `re.search`/`startswith`/`in`-de-string aqui aceitaria sufixos ou
    prefixos forjados (`https://ilya-rust.vercel.app.attacker.evil`)."""
    if origin in settings.get_cors_origins():
        return True
    origin_regex = settings.BACKEND_CORS_ORIGIN_REGEX
    return bool(origin_regex) and re.fullmatch(origin_regex, origin) is not None


def resolve_request_origin(request: Request) -> str | None:
    """Extrai a origem confiável do request.

    `Origin` tem prioridade; navegadores o anexam de forma não forjável por
    JavaScript em POSTs. `Origin: null` (iframe sandboxed, contexto opaco,
    redirect cross-scheme) nunca é tratado como origem válida — uma chamada
    same-origin real sempre envia o valor real, então "null" é sinal de
    contexto não confiável, não de ausência de cabeçalho.

    Na ausência do `Origin` (alguns navegadores antigos omitem em certas
    condições), cai para a origem derivada do `Referer`.
    """
    origin = request.headers.get("origin")
    if origin is not None:
        if origin == "null":
            return None
        return origin
    referer = request.headers.get("referer")
    if referer:
        return _referer_origin(referer)
    return None


def require_trusted_cookie_origin(request: Request) -> None:
    """CSRF (achado #3 do relatório de segurança 2026-07-28, endurecido na
    revisão independente do commit `6e77e01`): bloqueia POST autenticado pelo
    cookie de refresh quando a origem (Origin, com fallback em Referer) não
    está na allowlist do CORS — lista exata ou regex inteira.

    O cookie usa SameSite=None porque frontend (Vercel) e backend (Railway)
    ficam em domínios registráveis diferentes; por isso o navegador o envia
    mesmo em requisições cross-site, e o Sec-Fetch-Site de uma chamada
    LEGÍTIMA também seria "cross-site" — não dá pra usar esse cabeçalho como
    bloqueio absoluto nesta arquitetura. A defesa real é conferir a origem
    contra a mesma allowlist do CORS. Aplicado somente às rotas autenticadas
    por cookie (`/auth/refresh`, `/auth/logout`); login usa credenciais no
    corpo e as demais rotas usam Bearer token, estruturalmente imune a CSRF.
    """
    origin = resolve_request_origin(request)
    if origin is None or not is_trusted_origin(origin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origem não permitida.",
        )
