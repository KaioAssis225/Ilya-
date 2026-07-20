"""Inicialização segura para múltiplas réplicas.

Serializa migrações e seed por advisory lock do PostgreSQL e, depois, substitui
o processo pelo Uvicorn. Assim duas réplicas podem iniciar juntas sem executar
DDL concorrente.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ilya.startup")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.url import resolve_async_database_url


_STARTUP_LOCK_ID = 4_956_921_001


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} precisa ser um número inteiro.") from exc
    if value < 1:
        raise RuntimeError(f"{name} precisa ser maior que zero.")
    return value


async def prepare_database() -> None:
    lock_timeout = _positive_int("STARTUP_DB_LOCK_TIMEOUT_SECONDS", 1800)
    migration_timeout = _positive_int(
        "STARTUP_MIGRATION_TIMEOUT_SECONDS",
        900,
    )
    seed_timeout = _positive_int("STARTUP_SEED_TIMEOUT_SECONDS", 120)
    engine = create_async_engine(
        resolve_async_database_url(os.environ.get("DATABASE_URL")),
        poolclass=NullPool,
        # O advisory lock é de sessão e não precisa de uma transação aberta.
        # Manter esta conexão "idle in transaction" faz CREATE INDEX
        # CONCURRENTLY esperar por ela, enquanto o startup espera o Alembic:
        # um bloqueio circular que impede a API de iniciar em banco novo.
        isolation_level="AUTOCOMMIT",
        connect_args={"command_timeout": lock_timeout},
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": _STARTUP_LOCK_ID},
            )
            try:
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    check=True,
                    timeout=migration_timeout,
                )
                # O seed do admin é idempotente e opcional: sem ADMIN_EMAIL/
                # ADMIN_PASSWORD no ambiente (caso normal em produção, onde o
                # admin já existe) ele é pulado; uma falha aqui não pode
                # derrubar a API inteira em crash-loop.
                if os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"):
                    seed = subprocess.run(
                        [sys.executable, "seed_admin.py"],
                        timeout=seed_timeout,
                    )
                    if seed.returncode != 0:
                        logger.warning(
                            "seed_admin.py terminou com código %s; seguindo com o "
                            "boot — verifique o admin manualmente.",
                            seed.returncode,
                        )
                else:
                    logger.info(
                        "ADMIN_EMAIL/ADMIN_PASSWORD ausentes; seed do admin pulado."
                    )
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _STARTUP_LOCK_ID},
                )
    finally:
        await engine.dispose()


def start_server() -> None:
    # Um worker é o padrão seguro enquanto o rate limit usa memória local.
    # Aumente somente depois de configurar Redis e conferir o pool do Postgres.
    workers = _positive_int("WEB_CONCURRENCY", 1)
    max_requests = _positive_int("UVICORN_LIMIT_MAX_REQUESTS", 10_000)
    concurrency_limit = _positive_int("UVICORN_LIMIT_CONCURRENCY", 100)
    backlog = _positive_int("UVICORN_BACKLOG", 2048)
    port = _positive_int("PORT", 8000)
    forwarded_allow_ips = os.environ.get(
        "FORWARDED_ALLOW_IPS",
        "127.0.0.1,100.0.0.0/8",
    )
    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--proxy-headers",
        "--forwarded-allow-ips",
        forwarded_allow_ips,
        "--timeout-keep-alive",
        "5",
        "--timeout-graceful-shutdown",
        "30",
        "--limit-max-requests",
        str(max_requests),
        "--limit-concurrency",
        str(concurrency_limit),
        "--backlog",
        str(backlog),
        "--no-access-log",
    ]
    os.execv(sys.executable, args)


def main(arguments: list[str] | None = None) -> None:
    """Executa migration, servidor ou o fluxo legado completo.

    O modo padrão continua sendo ``all`` para não mudar o deploy atual. Depois
    que a infraestrutura possuir uma tarefa de migration dedicada, use
    ``python startup.py migrate`` nela e ``python startup.py serve`` no serviço
    web. Isso impede uma falha de DDL de reiniciar todas as réplicas da API.
    """
    selected = list(sys.argv[1:] if arguments is None else arguments)
    if len(selected) > 1 or (selected and selected[0] not in {"all", "migrate", "serve"}):
        raise RuntimeError("Modo inválido. Use: all, migrate ou serve.")

    mode = selected[0] if selected else "all"
    if mode in {"all", "migrate"}:
        asyncio.run(prepare_database())
    if mode in {"all", "serve"}:
        start_server()


if __name__ == "__main__":
    main()
