import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from limits.errors import StorageError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.routers.auth import _authenticate_credentials
from app.core.login_protection import enforce_login_cooldown, login_attempt_key
from app.main import _rate_limit_storage_unavailable
from app.schemas.auth import LoginRequest


def _request(host="203.0.113.10"):
    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers={},
        state=SimpleNamespace(request_id="test"),
    )


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def test_login_fingerprints_do_not_store_identifier_or_ip():
    key = login_attempt_key(_request(), "titular@example.com")
    assert key == login_attempt_key(_request(), "titular@example.com")
    assert key != login_attempt_key(_request("198.51.100.7"), "titular@example.com")
    assert "titular" not in key.identifier
    assert "203.0.113.10" not in key.origin


def test_cooldown_is_scoped_to_origin_and_identifier():
    async def run():
        now = datetime.now(timezone.utc)
        state = SimpleNamespace(cooldown_until=now + timedelta(seconds=30))
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(state)
        key = login_attempt_key(_request(), "conta@example.com")
        with pytest.raises(HTTPException) as exc:
            await enforce_login_cooldown(db, key, now=now)
        assert exc.value.status_code == 429
        assert int(exc.value.headers["Retry-After"]) >= 29

        other_origin = login_attempt_key(_request("198.51.100.7"), "conta@example.com")
        assert other_origin.origin != key.origin
    asyncio.run(run())


def test_invalid_password_records_pair_without_locking_user_globally():
    async def run():
        user = SimpleNamespace(
            id="user-id", is_active=True, hashed_password="hash",
            failed_login_attempts=4, locked_until=datetime.now(timezone.utc),
        )
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(user)
        with (
            patch("app.api.routers.auth.enforce_login_cooldown", AsyncMock()),
            patch(
                "app.api.routers.auth.record_login_failure",
                AsyncMock(return_value=(5, datetime.now(timezone.utc), 5)),
            ) as record,
            patch("app.api.routers.auth.verify_password", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc:
                await _authenticate_credentials(
                    _request(),
                    LoginRequest(identifier="conta@example.com", password="errada"),
                    db,
                )
        assert exc.value.status_code == 401
        record.assert_awaited_once()
        assert user.failed_login_attempts == 4
    asyncio.run(run())


def test_valid_password_clears_only_the_pair_and_legacy_lock():
    async def run():
        user = SimpleNamespace(
            id="user-id", is_active=True, hashed_password="hash",
            failed_login_attempts=4, locked_until=datetime.now(timezone.utc),
        )
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(user)
        with (
            patch("app.api.routers.auth.enforce_login_cooldown", AsyncMock()),
            patch("app.api.routers.auth.clear_login_failure", AsyncMock()) as clear,
            patch("app.api.routers.auth.verify_password", return_value=True),
        ):
            authenticated = await _authenticate_credentials(
                _request(),
                LoginRequest(identifier="conta@example.com", password="correta"),
                db,
            )
        assert authenticated is user
        clear.assert_awaited_once()
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
    asyncio.run(run())


def test_redis_failure_is_explicitly_fail_closed():
    response = _rate_limit_storage_unavailable(_request(), StorageError("down"))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_untrusted_peer_cannot_forge_forwarded_ip():
    observed = {}

    async def app(scope, _receive, _send):
        observed["client"] = scope["client"][0]

    middleware = ProxyHeadersMiddleware(app, trusted_hosts="100.64.0.0/10")
    scope = {
        "type": "http",
        "client": ("203.0.113.10", 40000),
        "headers": [(b"x-forwarded-for", b"1.1.1.1")],
    }
    asyncio.run(middleware(scope, AsyncMock(), AsyncMock()))
    assert observed["client"] == "203.0.113.10"


def test_trusted_proxy_uses_rightmost_untrusted_client():
    observed = {}

    async def app(scope, _receive, _send):
        observed["client"] = scope["client"][0]

    middleware = ProxyHeadersMiddleware(app, trusted_hosts="100.64.0.0/10")
    scope = {
        "type": "http",
        "client": ("100.64.1.5", 40000),
        "headers": [(b"x-forwarded-for", b"1.1.1.1, 198.51.100.8")],
    }
    asyncio.run(middleware(scope, AsyncMock(), AsyncMock()))
    assert observed["client"] == "198.51.100.8"
