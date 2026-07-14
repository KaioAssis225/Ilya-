import pytest
from sqlalchemy.engine import URL

from app.db.url import render_database_url, resolve_async_database_url


PG_NAMES = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")


def clear_pg(monkeypatch):
    for name in PG_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_database_url_fallback_for_local_environment(monkeypatch):
    clear_pg(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    assert resolve_async_database_url() == "postgresql+asyncpg://user:pass@localhost/db"


def test_pg_variables_encode_special_characters(monkeypatch):
    monkeypatch.setenv("PGHOST", "postgres.internal")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "user@example")
    monkeypatch.setenv("PGPASSWORD", "p@ss:/#word")
    monkeypatch.setenv("PGDATABASE", "ilya")
    value = resolve_async_database_url()
    assert isinstance(value, URL)
    rendered = render_database_url(value)
    assert "user%%40example" in rendered
    assert "p%%40ss%%3A%%2F%%23word" in rendered


def test_partial_pg_configuration_fails(monkeypatch):
    clear_pg(monkeypatch)
    monkeypatch.setenv("PGHOST", "postgres.internal")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback/db")
    with pytest.raises(RuntimeError, match="PGUSER"):
        resolve_async_database_url()


def test_invalid_pg_port_fails(monkeypatch):
    for name, value in {
        "PGHOST": "postgres.internal",
        "PGPORT": "invalid",
        "PGUSER": "user",
        "PGPASSWORD": "pass",
        "PGDATABASE": "ilya",
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="PGPORT"):
        resolve_async_database_url()
