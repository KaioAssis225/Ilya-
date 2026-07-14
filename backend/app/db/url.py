"""Resolução centralizada e segura da URL assíncrona do PostgreSQL."""

from __future__ import annotations

import os

from sqlalchemy.engine import URL


PG_VARIABLES = ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE")


def resolve_async_database_url(fallback_url: str | None = None) -> str | URL:
    """Prefere PG* do Railway e mantém DATABASE_URL para Docker/testes locais."""
    pg_values = {name: os.environ.get(name, "") for name in PG_VARIABLES}
    configured = [name for name, value in pg_values.items() if value]
    if configured:
        missing = [name for name, value in pg_values.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing required Postgres environment variable(s): "
                f"{', '.join(missing)}. Configure todas as variaveis PG* ou use DATABASE_URL."
            )
        try:
            port = int(os.environ.get("PGPORT", "5432"))
        except ValueError as exc:
            raise RuntimeError("PGPORT precisa ser um numero inteiro valido.") from exc
        return URL.create(
            "postgresql+asyncpg",
            username=pg_values["PGUSER"],
            password=pg_values["PGPASSWORD"],
            host=pg_values["PGHOST"],
            port=port,
            database=pg_values["PGDATABASE"],
        )

    database_url = os.environ.get("DATABASE_URL", "") or fallback_url or ""
    if not database_url:
        raise RuntimeError(
            "Database configuration missing. Configure PGHOST, PGUSER, PGPASSWORD, "
            "PGDATABASE e PGPORT, ou defina DATABASE_URL."
        )
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def render_database_url(value: str | URL) -> str:
    """Renderiza sem ocultar senha; Alembic exige escape de percentuais."""
    rendered = value.render_as_string(hide_password=False) if isinstance(value, URL) else value
    return rendered.replace("%", "%%")
