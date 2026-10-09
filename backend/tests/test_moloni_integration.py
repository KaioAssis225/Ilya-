import asyncio
import uuid
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
        def raise_for_status(self): pass
        def json(self): return {"valid": 1}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, *args, **kwargs): captured.update(kwargs); return Response()
    monkeypatch.setattr(moloni_exporter, "decrypt_token", lambda _: "token")
    monkeypatch.setattr(moloni_exporter.httpx, "AsyncClient", lambda **_: Client())
    api = moloni_exporter.MoloniApi(SimpleNamespace(access_token_ciphertext="cipher"))
    asyncio.run(api.post("estimates/insert", {"products": [{"taxes": [{"tax_id": 1}]}]}))
    assert captured["params"]["json"] == "true"
    assert captured["json"]["products"][0]["taxes"][0]["tax_id"] == 1
