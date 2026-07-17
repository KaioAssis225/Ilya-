"""Inicialização segura para múltiplas réplicas.

Serializa migrações e seed por advisory lock do PostgreSQL e, depois, substitui
o processo pelo Uvicorn. Assim duas réplicas podem iniciar juntas sem executar
DDL concorrente.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

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
                subprocess.run(
                    [sys.executable, "seed_admin.py"],
                    check=True,
                    timeout=seed_timeout,
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


if __name__ == "__main__":
    asyncio.run(prepare_database())
    start_server()
