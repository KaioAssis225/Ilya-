"""CSRF (revisão independente do achado #3, relatório 2026-07-28 / commit
`6e77e01`): cobre a validação de origem usada em `/auth/refresh` e
`/auth/logout` — allowlist exata + regex inteira, `Origin: null`, fallback
em `Referer`, e o caso de ambos ausentes."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.origin_guard import (
    is_trusted_origin,
    require_trusted_cookie_origin,
    resolve_request_origin,
)


def _request(headers: dict[str, str]) -> Request:
    encoded = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    scope = {"type": "http", "headers": encoded}
    return Request(scope)


class TestIsTrustedOrigin:
    def test_stable_production_alias_allowed(self):
        assert is_trusted_origin("https://ilya-rust.vercel.app") is True

    def test_vercel_preview_deployment_allowed_by_regex(self):
        assert is_trusted_origin(
            "https://ilya-atyyjocxe-kaioassis225s-projects.vercel.app"
        ) is True

    def test_attacker_domain_rejected(self):
        assert is_trusted_origin("https://attacker.evil") is False

    def test_lookalike_suffix_domain_rejected(self):
        # Regressão-alvo: fullmatch, não startswith/in/search — um "contains"
        # aceitaria isso por conter o domínio real como prefixo.
        assert is_trusted_origin(
            "https://ilya-rust.vercel.app.attacker.evil"
        ) is False

    def test_lookalike_prefix_domain_rejected(self):
        assert is_trusted_origin(
            "https://attacker.evil.ilya-rust.vercel.app"
        ) is False

    def test_other_vercel_project_rejected(self):
        assert is_trusted_origin(
            "https://outro-projeto-outra-conta.vercel.app"
        ) is False


class TestResolveRequestOrigin:
    def test_origin_header_used_when_present(self):
        request = _request({"origin": "https://ilya-rust.vercel.app"})
        assert resolve_request_origin(request) == "https://ilya-rust.vercel.app"

    def test_origin_null_is_not_a_valid_origin(self):
        request = _request({"origin": "null"})
        assert resolve_request_origin(request) is None

    def test_missing_origin_falls_back_to_referer(self):
        request = _request(
            {"referer": "https://ilya-rust.vercel.app/pedidos/123"}
        )
        assert resolve_request_origin(request) == "https://ilya-rust.vercel.app"

    def test_missing_origin_and_referer_resolves_to_none(self):
        request = _request({})
        assert resolve_request_origin(request) is None

    def test_malformed_referer_resolves_to_none(self):
        request = _request({"referer": "not-a-url"})
        assert resolve_request_origin(request) is None


class TestRequireTrustedCookieOrigin:
    def test_legitimate_stable_origin_passes(self):
        request = _request({"origin": "https://ilya-rust.vercel.app"})
        require_trusted_cookie_origin(request)  # não deve levantar

    def test_legitimate_preview_origin_passes(self):
        request = _request(
            {"origin": "https://ilya-atyyjocxe-kaioassis225s-projects.vercel.app"}
        )
        require_trusted_cookie_origin(request)  # não deve levantar

    def test_referer_fallback_with_legitimate_domain_passes(self):
        request = _request(
            {"referer": "https://ilya-rust.vercel.app/pedidos"}
        )
        require_trusted_cookie_origin(request)  # não deve levantar

    def test_malicious_origin_rejected_with_403(self):
        request = _request({"origin": "https://attacker.evil"})
        with pytest.raises(HTTPException) as exc:
            require_trusted_cookie_origin(request)
        assert exc.value.status_code == 403

    def test_origin_null_rejected_with_403(self):
        request = _request({"origin": "null"})
        with pytest.raises(HTTPException) as exc:
            require_trusted_cookie_origin(request)
        assert exc.value.status_code == 403

    def test_missing_origin_and_referer_rejected_with_403(self):
        request = _request({})
        with pytest.raises(HTTPException) as exc:
            require_trusted_cookie_origin(request)
        assert exc.value.status_code == 403

    def test_lookalike_suffix_domain_rejected_with_403(self):
        request = _request(
            {"origin": "https://ilya-rust.vercel.app.attacker.evil"}
        )
        with pytest.raises(HTTPException) as exc:
            require_trusted_cookie_origin(request)
        assert exc.value.status_code == 403
