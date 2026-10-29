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


def test_moloni_http_error_does_not_leak_access_token(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PASSWORD_PEPPER", "test-pepper")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    import httpx
    import pytest
    from app.services import moloni_exporter

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def post(self, url, params=None, **_kwargs):
            request = httpx.Request("POST", url, params=params)
            return httpx.Response(400, request=request)

    monkeypatch.setattr(moloni_exporter, "decrypt_token", lambda _: "tok-secreto")
    monkeypatch.setattr(moloni_exporter.httpx, "AsyncClient", lambda **_: Client())
    api = moloni_exporter.MoloniApi(SimpleNamespace(access_token_ciphertext="cipher", token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)), SimpleNamespace())
    with pytest.raises(moloni_exporter.MoloniError) as exc:
        asyncio.run(api.post("estimates/insert", {}))
    assert "tok-secreto" not in str(exc.value)
    assert "400" in str(exc.value)


def test_moloni_resolves_nested_article_category_without_recreating_it():
    from app.services.moloni_exporter import _resolve_product_category_id

    class Api:
        def __init__(self): self.calls = []
        async def post(self, endpoint, payload):
            self.calls.append((endpoint, payload))
            if endpoint == "productCategories/getAll":
                if payload["parent_id"] == 0:
                    return [{"category_id": 12, "name": "Móveis"}]
                return [{"category_id": 34, "name": "Cadeiras"}]
            raise AssertionError(endpoint)

    api = Api()
    assert asyncio.run(_resolve_product_category_id(api, 1, "Móveis / Cadeiras")) == 34
    assert [call[1]["parent_id"] for call in api.calls] == [0, 12]


def test_moloni_creates_missing_article_category_under_parent():
    from app.services.moloni_exporter import _resolve_product_category_id

    class Api:
        def __init__(self): self.calls = []
        async def post(self, endpoint, payload):
            self.calls.append((endpoint, payload))
            if endpoint == "productCategories/getAll":
                return [{"category_id": 12, "name": "Móveis"}] if payload["parent_id"] == 0 else []
            if endpoint == "productCategories/insert":
                return {"category_id": 34}
            raise AssertionError(endpoint)

    api = Api()
    assert asyncio.run(_resolve_product_category_id(api, 1, "Móveis / Cadeiras")) == 34
    assert api.calls[-1] == ("productCategories/insert", {"company_id": 1, "parent_id": 12, "name": "Cadeiras"})


def test_product_article_metadata_normalizes_path_and_blank_fields():
    from app.schemas.product import ProductUpdate

    product = ProductUpdate(ean="  ", summary="  Resumo  ", article_category_path=" Móveis / Cadeiras ")
    assert product.ean is None
    assert product.summary == "Resumo"
    assert product.article_category_path == "Móveis / Cadeiras"


def test_moloni_tax_payload_requires_explicit_nonzero_rate():
    import pytest
    from app.services.moloni_exporter import MoloniError, _tax_for_rate

    assert _tax_for_rate("23.00", {"23.00": 7}) == {
        "tax_id": 7, "value": 23.0, "order": 1, "cumulative": 0,
    }
    with pytest.raises(MoloniError, match="motivo de isenção"):
        _tax_for_rate("0.00", {"0.00": 8})


def test_moloni_line_summary_keeps_every_application_choice():
    from app.services.moloni_exporter import _line_summary

    first = SimpleNamespace(id=uuid.uuid4(), display_order=0, component_name="Assento",
                            application_name="Couro do assento", application_name_en="Seat leather",
                            optional_name="Caramelo", custom_text=None)
    second = SimpleNamespace(id=uuid.uuid4(), display_order=1, component_name=None,
                             application_name="Pintura dos pés", application_name_en="Leg paint",
                             optional_name="Customizado", custom_text="Pés em latão")
    item = SimpleNamespace(opt_categories={"CORDA": "Natural"}, optional_choices=[second, first], comment="Entregar montado")
    assert _line_summary("Resumo", item, "en-GB") == (
        "Resumo\nCORDA: Natural\nAssento — Seat leather: Caramelo\nLeg paint: Custom: Pés em latão\nComment: Entregar montado"
    )


def test_moloni_line_summary_shows_rug_measurements_and_pieces():
    from app.services.moloni_exporter import _line_summary
    from decimal import Decimal

    item_pt = SimpleNamespace(
        sold_by_area=True,
        area_width_m=Decimal("2.05"),
        area_depth_m=Decimal("3.000"),
        area_pieces=2,
        opt_categories={},
        optional_choices=[],
        comment=None,
    )
    summary_pt = _line_summary("Resumo", item_pt, "pt-PT")
    assert "Medidas: 2,05 × 3 m × 2 peças" in summary_pt

    item_en = SimpleNamespace(
        sold_by_area=True,
        area_width_m=Decimal("2.00"),
        area_depth_m=Decimal("2.00"),
        area_pieces=1,
        opt_categories={},
        optional_choices=[],
        comment=None,
    )
    summary_en = _line_summary("Resumo", item_en, "en-GB")
    assert "Dimensions: 2 × 2 m" in summary_en
    assert "pieces" not in summary_en
