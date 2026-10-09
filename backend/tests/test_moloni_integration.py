import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.moloni_jobs import enqueue_finalized_eu_order


class _Result:
    def __init__(self, value=None): self.value = value
    def scalar_one_or_none(self): return self.value


class _Db:
    def __init__(self): self.statements = []
    async def execute(self, statement): self.statements.append(statement); return _Result()


def test_finalized_eu_enqueue_uses_conflict_safe_insert():
    db = _Db()
    asyncio.run(enqueue_finalized_eu_order(db, uuid.uuid4()))
    compiled = str(db.statements[0].compile(dialect=__import__('sqlalchemy').dialects.postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_moloni_export_jobs_order DO NOTHING" in compiled


def test_oauth_url_encodes_redirect(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PASSWORD_PEPPER", "test-pepper")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    from app.api.routers import moloni
    monkeypatch.setattr(moloni.settings, "MOLONI_CLIENT_ID", "client id", raising=False)
    monkeypatch.setattr(moloni.settings, "MOLONI_CLIENT_SECRET", "secret", raising=False)
    monkeypatch.setattr(moloni.settings, "MOLONI_REDIRECT_URI", "https://site/callback?a=1", raising=False)
    db = SimpleNamespace(add=lambda x: None, commit=lambda: None)
    async def commit(): return None
    db.commit = commit
    platform = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()))
    result = asyncio.run(moloni.connect(moloni.ConnectRequest(company_id=5), db, platform))
    assert "redirect_uri=https%3A%2F%2Fsite%2Fcallback%3Fa%3D1" in result["authorization_url"]
    assert "state=" in result["authorization_url"]


def test_moloni_uses_json_mode_for_nested_document_data(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PASSWORD_PEPPER", "test-pepper")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    from app.services import moloni_exporter
    captured = {}
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"valid": 1}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, *args, **kwargs): captured.update(kwargs); return Response()
    monkeypatch.setattr(moloni_exporter, "decrypt_token", lambda _: "token")
    monkeypatch.setattr(moloni_exporter.httpx, "AsyncClient", lambda **_: Client())
    api = moloni_exporter.MoloniApi(SimpleNamespace(access_token_ciphertext="cipher", token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)), SimpleNamespace())
    asyncio.run(api.post("estimates/insert", {"products": [{"taxes": [{"tax_id": 1}]}]}))
    assert captured["params"]["json"] == "true"
    assert captured["json"]["products"][0]["taxes"][0]["tax_id"] == 1


def test_moloni_refreshes_expiring_token(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PASSWORD_PEPPER", "test-pepper")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    from app.services import moloni_exporter

    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, *args, **kwargs): calls.append((args, kwargs)); return Response()
    class Db:
        async def flush(self): pass
    connection = SimpleNamespace(
        access_token_ciphertext="access-cipher",
        refresh_token_ciphertext="refresh-cipher",
        token_expires_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(moloni_exporter, "decrypt_token", lambda value: {"access-cipher": "old-access", "refresh-cipher": "old-refresh"}[value])
    monkeypatch.setattr(moloni_exporter, "encrypt_token", lambda value: "encrypted:" + value)
    monkeypatch.setattr(moloni_exporter.httpx, "AsyncClient", lambda **_: Client())
    api = moloni_exporter.MoloniApi(connection, Db())
    asyncio.run(api._refresh_if_needed())
    assert api.token == "new-access"
    assert connection.access_token_ciphertext == "encrypted:new-access"
    assert calls[0][1]["params"]["grant_type"] == "refresh_token"


def test_moloni_retries_once_after_server_rejects_token(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PASSWORD_PEPPER", "test-pepper")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    from app.services import moloni_exporter

    responses = []
    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {"valid": 1}
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)
        def json(self): return self._payload

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, *args, **kwargs):
            response = Response(403 if not responses else 200)
            responses.append(response)
            return response

    connection = SimpleNamespace(
        access_token_ciphertext="cipher",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    monkeypatch.setattr(moloni_exporter, "decrypt_token", lambda _: "old-access")
    api = moloni_exporter.MoloniApi(connection, SimpleNamespace())
    api.token = "old-access"
    async def refresh(): api.token = "new-access"
    api._refresh_if_needed = refresh
    monkeypatch.setattr(moloni_exporter.httpx, "AsyncClient", lambda **_: Client())

    asyncio.run(api.post("customers/getByVat", {"company_id": 1, "vat": "123456789"}))
    assert len(responses) == 2
    assert api.token == "new-access"
    assert connection.token_expires_at is None
