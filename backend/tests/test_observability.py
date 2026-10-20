import asyncio
from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.core import observability as obs

pytestmark = pytest.mark.contract


@pytest.fixture
def enabled_registry(monkeypatch):
    registry = obs.Registry()
    monkeypatch.setattr(obs, "ENABLED", True)
    monkeypatch.setattr(obs, "registry", registry)
    return registry


def _scope(path: str = "/api/v1/orders/real-id") -> dict:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "route": SimpleNamespace(path="/api/v1/orders/{order_id}"),
    }


def test_flag_off_does_not_collect_or_expose(monkeypatch):
    registry = obs.Registry()
    monkeypatch.setattr(obs, "ENABLED", False)
    registry.counter("ilya_http_requests_total", route="/private")
    assert "ilya_http_requests_total" not in registry.render()

    from app import main
    request = Request(_scope("/internal/metrics"))
    response = asyncio.run(main.observability_metrics(request))
    assert response.status_code == 404


def test_metrics_endpoint_requires_exact_bearer_token(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "OBSERVABILITY_ENABLED", True)
    monkeypatch.setattr(main.settings, "OBSERVABILITY_METRICS_TOKEN", "collector-secret")
    denied = asyncio.run(main.observability_metrics(Request(_scope("/internal/metrics"))))
    assert denied.status_code == 404

    scope = _scope("/internal/metrics")
    scope["headers"] = [(b"authorization", b"Bearer collector-secret")]
    allowed = asyncio.run(main.observability_metrics(Request(scope)))
    assert allowed.status_code == 200
    assert b"ilya_app_info" in allowed.body


def test_request_id_is_preserved_and_invalid_value_is_replaced():
    from app.main import add_request_id

    async def call(header: bytes):
        scope = _scope("/health")
        scope["headers"] = [(b"x-request-id", header)]
        request = Request(scope)
        response = await add_request_id(request, lambda _request: _response())
        return request.state.request_id, response.headers["X-Request-ID"]

    async def _response():
        return Response("ok")

    supplied, echoed = asyncio.run(call(b"benchmark-01"))
    assert supplied == echoed == "benchmark-01"
    generated, echoed = asyncio.run(call(b"email@example.com"))
    assert generated == echoed
    assert generated != "email@example.com"


def test_http_uses_route_template_and_bounded_market(enabled_registry):
    scope = _scope()
    route = obs.safe_route(scope)
    obs.http_started("GET")
    obs.http_finished(
        method="GET", route=route, status=200, market="BR", duration=0.02,
        response_bytes=123,
    )
    obs.http_started("TRACE")
    obs.http_finished(
        method="TRACE", route=route, status=503, market="PT", duration=0.03,
        response_bytes=None,
    )
    rendered = enabled_registry.render()
    assert '/api/v1/orders/{order_id}' in rendered
    assert "real-id" not in rendered
    assert 'market="BR"' in rendered
    assert 'market="none"' in rendered
    assert 'method="OTHER"' in rendered


def test_unmapped_route_never_falls_back_to_real_path():
    scope = _scope("/api/v1/orders/5fd4f6aa-22b8-49b9-8444-915490ad63af")
    scope.pop("route")
    assert obs.safe_route(scope) == "unmapped"


def test_external_failure_keeps_only_allowlisted_dependency(enabled_registry):
    secret_url = "https://evil.invalid/12345678?email=person@example.com&token=secret"
    request = httpx.Request("GET", secret_url)
    request.extensions["ilya_observability_started"] = 1.0
    obs.external_exception(httpx.ConnectError("failed", request=request))
    obs.external_invalid("attacker-controlled-label")
    rendered = enabled_registry.render()
    assert 'dependency="unknown"' in rendered
    for secret in ("evil.invalid", "12345678", "person@example.com", "token", "secret"):
        assert secret not in rendered


def test_dependency_allowlist_and_fallback(enabled_registry):
    request = httpx.Request("GET", "https://json.geoapi.pt/cp/1000-001")
    assert obs.dependency_name(request) == "geoapi"
    obs.external_fallback("geoapi")
    rendered = enabled_registry.render()
    assert 'ilya_external_fallbacks_total{dependency="geoapi"} 1' in rendered


def test_request_totals_correlate_external_time_without_metric_id(enabled_registry):
    token = obs.begin_request()
    try:
        obs.external_observe("viacep", status=200, outcome="http", duration=0.125)
        totals = obs.request_totals()
    finally:
        obs.end_request(token)
    assert totals["external_count"] == 1
    assert totals["external_seconds"] == pytest.approx(0.125)
    assert "request_id" not in enabled_registry.render()
