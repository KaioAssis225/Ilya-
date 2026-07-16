import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import AsyncSessionLocal
from app.models.refresh_token import cleanup_expired_tokens
from app.api.routers import products_router, clients_router, reps_router, orders_router, optionals_router, product_types_router, product_groups_router, optional_categories_router, users_router, notifications_router, utils_router, import_router, dashboard_router
from app.api.routers.auth import router as auth_router

# ── Logging estruturado ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ilya")


async def _cleanup_tokens_background() -> None:
    try:
        async with AsyncSessionLocal() as session:
            await cleanup_expired_tokens(
                session,
                settings.REFRESH_TOKEN_AUDIT_RETENTION_DAYS,
            )
    except Exception:
        logger.exception("Falha na limpeza de refresh tokens expirados")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Limpeza em background: não bloqueia a prontidão da API a cada boot
    # (a tabela cresce com o uso e o DELETE não tem índice em expires_at).
    cleanup_task = asyncio.create_task(_cleanup_tokens_background())
    logger.info("Ilya API iniciada")
    yield
    cleanup_task.cancel()
    logger.info("Ilya API encerrada")


app = FastAPI(
    title="Projeto Ilya API",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Rate limit handler ────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_origins = settings.get_cors_origins()
if "*" in _cors_origins:
    # Wildcard nunca é seguro com allow_credentials=True (V-Bloco66-CORS).
    raise RuntimeError("BACKEND_CORS_ORIGINS não pode conter '*' — configure as origens explícitas no .env.")
if not settings.DEBUG and all("localhost" in o or "127.0.0.1" in o for o in _cors_origins):
    logger.warning(
        "BACKEND_CORS_ORIGINS aponta só para localhost em ambiente não-DEBUG (%s). "
        "Confirme se isso é intencional antes do deploy.", _cors_origins,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Request-ID"],
)


# ── Security headers middleware ───────────────────────────────────────────────
# Os headers são idênticos para todas as respostas — montados uma única vez no
# load do módulo em vez de re-avaliar o branch de DEBUG a cada request.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}
if settings.DEBUG:
    # unsafe-inline necessário para Tailwind v4 em dev (injeta <style> no head)
    # e para o Swagger UI servido em /docs. Fontes agora são self-hosted
    # via @fontsource (LGPD L-01) — sem domínios do Google.
    _SECURITY_HEADERS["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self';"
    )
else:
    _SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    # Em produção o backend serve apenas API JSON e /static (imagens) —
    # nenhuma página HTML própria, então a CSP pode ser estrita (V-03).
    _SECURITY_HEADERS["Content-Security-Policy"] = (
        "default-src 'none'; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(_SECURITY_HEADERS)
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(clients_router)
app.include_router(reps_router)
app.include_router(orders_router)
app.include_router(optionals_router)
app.include_router(product_types_router)
app.include_router(product_groups_router)
app.include_router(optional_categories_router)
app.include_router(notifications_router)
app.include_router(utils_router)
app.include_router(import_router)
app.include_router(dashboard_router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/health/live", tags=["health"])
async def liveness_check():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness falhou ao consultar o banco")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready", "version": settings.APP_VERSION}
