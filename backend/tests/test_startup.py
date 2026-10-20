import asyncio
import json
from pathlib import Path

import pytest

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

    async def fake_prepare_database(*, include_seed):
        calls.append(("migrate", include_seed))

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main(["migrate"])

    assert calls == [("migrate", False)]


def test_serve_mode_does_not_run_migrations(monkeypatch):
    calls = []

    async def fake_prepare_database(*, include_seed):
        calls.append(("migrate", include_seed))

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main(["serve"])

    assert calls == ["serve"]


def test_default_mode_preserves_current_deploy_behavior(monkeypatch):
    calls = []

    async def fake_prepare_database(*, include_seed):
        calls.append(("migrate", include_seed))

    monkeypatch.setattr(startup, "prepare_database", fake_prepare_database)
    monkeypatch.setattr(startup, "start_server", lambda: calls.append("serve"))

    startup.main([])

    assert calls == [("migrate", True), "serve"]


@pytest.mark.parametrize("arguments", [["invalid"], ["serve", "extra"], ["migrate", "serve"]])
def test_main_rejects_invalid_mode_or_extra_arguments(arguments):
    with pytest.raises(RuntimeError, match="Modo inválido. Use: all, migrate ou serve."):
        startup.main(arguments)


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "::/0", "invalid-host"])
def test_proxy_trust_rejects_unsafe_values(value):
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS|internet|inválido"):
        startup._validated_forwarded_allow_ips(value)


def test_proxy_trust_accepts_only_explicit_networks():
    assert startup._validated_forwarded_allow_ips(
        "127.0.0.1, 100.64.0.0/10"
    ) == "127.0.0.1,100.64.0.0/10"


def test_multiple_workers_require_shared_rate_limit_storage():
    with pytest.raises(RuntimeError, match="Redis"):
        startup._validate_rate_limit_workers(2, "memory://")
    startup._validate_rate_limit_workers(2, "redis://redis.internal:6379/0")


def test_dockerfile_prod_uses_serve_and_railway_json_preserves_predeploy_migrate():
    backend_dir = Path(__file__).resolve().parents[1]

    dockerfile_content = (backend_dir / "Dockerfile.prod").read_text(encoding="utf-8")
    assert 'CMD ["python", "startup.py", "serve"]' in dockerfile_content

    railway_data = json.loads((backend_dir / "railway.json").read_text(encoding="utf-8"))
    deploy = railway_data.get("deploy", railway_data)
    pre_deploy = deploy.get("preDeployCommand", [])
    pre_deploy_str = " ".join(pre_deploy) if isinstance(pre_deploy, list) else str(pre_deploy)
    assert "python startup.py migrate" in pre_deploy_str
    assert deploy.get("healthcheckPath") == "/health/ready"
