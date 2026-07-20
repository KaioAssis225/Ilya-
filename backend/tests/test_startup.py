import asyncio

import startup


class _Connection:
    def __init__(self, statements: list[str]):
        self.statements = statements

    async def execute(self, statement, _parameters=None):
        self.statements.append(str(statement))


class _ConnectionContext:
    def __init__(self, connection: _Connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _Engine:
    def __init__(self, connection: _Connection):
        self.connection = connection
        self.disposed = False

    def connect(self):
        return _ConnectionContext(self.connection)

    async def dispose(self):
        self.disposed = True


def test_startup_lock_connection_uses_autocommit(monkeypatch):
    captured = {}
    statements: list[str] = []
    engine = _Engine(_Connection(statements))

    def fake_create_async_engine(url, **options):
        captured["url"] = url
        captured.update(options)
        return engine

    monkeypatch.setattr(startup, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(startup.subprocess, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ilya_test",
    )
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    asyncio.run(startup.prepare_database())

    assert captured["isolation_level"] == "AUTOCOMMIT"
    assert any("pg_advisory_lock" in statement for statement in statements)
    assert any("pg_advisory_unlock" in statement for statement in statements)
    assert engine.disposed is True


def test_migrate_mode_does_not_start_web_server(monkeypatch):
    calls = []

    async def fake_prepare_database():
        calls.append("migrate")

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main(["migrate"])

    assert calls == ["migrate"]


def test_serve_mode_does_not_run_migrations(monkeypatch):
    calls = []

    async def fake_prepare_database():
        calls.append("migrate")

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main(["serve"])

    assert calls == ["serve"]


def test_default_mode_preserves_current_deploy_behavior(monkeypatch):
    calls = []

    async def fake_prepare_database():
        calls.append("migrate")

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main([])

    assert calls == ["migrate", "serve"]
