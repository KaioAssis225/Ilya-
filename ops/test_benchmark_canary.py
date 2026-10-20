"""Contratos de segurança do benchmark técnico P11; execução no checkpoint."""

import io
import json
import urllib.error

import pytest

from ops import benchmark_production_api as benchmark
from ops.benchmark_scenarios import select_scenarios


class FakeResponse:
    def __init__(self, data):
        self.payload = io.BytesIO(json.dumps(data).encode())

    def __enter__(self):
        return self.payload

    def __exit__(self, *_args):
        self.payload.close()


def test_catalogue_is_get_only_and_rejects_unauthenticated_commercial():
    with pytest.raises(ValueError):
        select_scenarios(authenticated=False, commercial=True)
    scenarios = select_scenarios(authenticated=True, commercial=True)
    assert all(s.route_template.startswith("GET ") and s.expected_status == 200 for s in scenarios)
    assert all("market=" not in s.path and "{" not in s.path for s in scenarios)


def test_canary_fails_closed_on_other_market_or_role(monkeypatch):
    def fake_open(request, timeout):
        if request.full_url.endswith("/login"):
            return FakeResponse({"access_token": "synthetic-token"})
        return FakeResponse({
            "active_market": "EU", "allowed_markets": ["EU"],
            "role": "produtos", "can_approve_tax": False,
        })

    monkeypatch.setattr(benchmark, "_open_no_redirect", fake_open)
    auth = benchmark.CanaryAuth("https://staging.example.invalid", "canary", "secret", "BR")
    auth.login()
    with pytest.raises(RuntimeError, match="vínculo exclusivo"):
        auth.verify_scope()


def test_canary_renews_after_401_without_exposing_secret(monkeypatch):
    issued = iter(("first-token", "second-token"))

    def fake_open(request, timeout):
        if request.full_url.endswith("/login"):
            return FakeResponse({"access_token": next(issued)})
        return FakeResponse({
            "active_market": "BR", "allowed_markets": ["BR"],
            "role": "benchmark_readonly", "can_approve_tax": False,
        })

    calls = []

    def fake_get(url, headers, timeout):
        calls.append(headers["Authorization"])
        return (401, 1.0, None) if len(calls) == 1 else (200, 2.0, None)

    monkeypatch.setattr(benchmark, "_open_no_redirect", fake_open)
    monkeypatch.setattr(benchmark, "make_request", fake_get)
    auth = benchmark.CanaryAuth("https://staging.example.invalid", "canary", "secret", "BR")
    assert auth.get("https://staging.example.invalid/api/v1/orders", 10)[0] == 200
    assert calls == ["Bearer first-token", "Bearer second-token"]


def test_login_failure_never_formats_password_or_token(monkeypatch):
    def fake_open(_request, _timeout):
        raise urllib.error.URLError("sensitive-password-and-token")

    monkeypatch.setattr(benchmark, "_open_no_redirect", fake_open)
    auth = benchmark.CanaryAuth("https://staging.example.invalid", "canary", "sensitive-password", "BR")
    with pytest.raises(RuntimeError) as exc:
        auth.login()
    assert "sensitive" not in str(exc.value)


def test_fixture_is_discovered_by_exact_code_and_market(monkeypatch):
    fixture_id = "12345678-1234-4234-8234-123456789abc"
    seen = []

    def fake_open(request, timeout):
        seen.append(request.full_url)
        return FakeResponse([
            {"id": fixture_id, "code": "SYN-ORDER-1", "market_code": "EU"},
            {"id": fixture_id, "code": "SYN-ORDER-2", "market_code": "BR"},
        ])

    monkeypatch.setattr(benchmark, "_open_no_redirect", fake_open)
    auth = benchmark.CanaryAuth("https://staging.example.invalid", "canary", "secret", "BR")
    auth._token = "synthetic-token"
    assert auth.resolve_fixture_id("/api/v1/orders", "code", "SYN-ORDER-2") == fixture_id
    assert "q=SYN-ORDER-2" in seen[0]
    with pytest.raises(ValueError):
        auth.resolve_fixture_id("/api/v1/orders", "code", "bad&parameter")
