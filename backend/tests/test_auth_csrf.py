"""CSRF (revisão independente do achado #3, relatório 2026-07-28 / commit
`6e77e01`): prova, via TestClient, que `require_trusted_cookie_origin` está
de fato conectado em `/auth/refresh` e `/auth/logout`, e que uma origem
rejeitada nunca chega a tocar o banco — ou seja, nenhuma sessão é rotacionada
ou revogada quando a origem é maliciosa."""
from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.main import app

_LEGITIMATE_ORIGIN = "https://ilya-rust.vercel.app"
_MALICIOUS_ORIGIN = "https://attacker.evil"
_FAKE_REFRESH_COOKIE = "fake-refresh-token-value"


class _NoRowResult:
    def scalar_one_or_none(self):
        return None


class _SpySession:
    """Substitui `get_db_session`: nunca toca um banco real, só registra
    se a rota chegou a tentar consultar/gravar algo."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, *_args, **_kwargs):
        self.calls.append("execute")
        return _NoRowResult()

    async def commit(self):
        self.calls.append("commit")

    def add(self, *_args, **_kwargs):
        self.calls.append("add")


def _client_with_spy_session(*, with_cookie: bool = True):
    spy = _SpySession()

    async def _override():
        yield spy

    app.dependency_overrides[get_db_session] = _override
    client = TestClient(app)
    if with_cookie:
        client.cookies.set("ilya_refresh", _FAKE_REFRESH_COOKIE)
    return client, spy


def _reset_overrides():
    app.dependency_overrides.pop(get_db_session, None)


class TestRefreshOriginGuard:
    def test_anonymous_session_returns_204_without_touching_db(self):
        client, spy = _client_with_spy_session(with_cookie=False)
        try:
            response = client.post(
                "/api/v1/auth/refresh",
                headers={"Origin": _LEGITIMATE_ORIGIN},
            )
            assert response.status_code == 204
            assert spy.calls == []
        finally:
            _reset_overrides()

    def test_malicious_origin_rejected_and_db_never_touched(self):
        client, spy = _client_with_spy_session()
        try:
            response = client.post(
                "/api/v1/auth/refresh",
                headers={"Origin": _MALICIOUS_ORIGIN},
            )
            assert response.status_code == 403
            assert spy.calls == []
        finally:
            _reset_overrides()

    def test_legitimate_origin_reaches_route_logic(self):
        client, spy = _client_with_spy_session()
        try:
            response = client.post(
                "/api/v1/auth/refresh",
                headers={"Origin": _LEGITIMATE_ORIGIN},
            )
            # Token falso não existe no banco -> 401, mas a rota FOI executada
            # (prova que a origem legítima passa pelo guard).
            assert response.status_code == 401
            assert "execute" in spy.calls
        finally:
            _reset_overrides()


class TestLogoutOriginGuard:
    def test_malicious_origin_rejected_and_db_never_touched(self):
        client, spy = _client_with_spy_session()
        try:
            response = client.post(
                "/api/v1/auth/logout",
                headers={"Origin": _MALICIOUS_ORIGIN},
            )
            assert response.status_code == 403
            assert spy.calls == []
        finally:
            _reset_overrides()

    def test_legitimate_origin_reaches_route_logic(self):
        client, spy = _client_with_spy_session()
        try:
            response = client.post(
                "/api/v1/auth/logout",
                headers={"Origin": _LEGITIMATE_ORIGIN},
            )
            assert response.status_code == 204
            assert "execute" in spy.calls
        finally:
            _reset_overrides()
