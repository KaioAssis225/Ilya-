import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.deps import get_market_principal, get_platform_principal, require_platform_capability
from app.api.routers.auth import login, platform_login, switch_market
from app.api.routers.markets import VatDecisionRequest, decide_europe_vat
from app.core.markets import MARKETS, MarketPrincipal, PlatformPrincipal
from app.core.security import create_access_token, decode_access_token
from app.models.market import UserMarket
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, SwitchMarketRequest


def _user(**overrides):
    values = {
        "id": uuid.uuid4(),
        "email": "admin@example.com",
        "username": "admin",
        "hashed_password": "hash",
        "full_name": "Admin",
        "role": UserRole.admin,
        "is_active": True,
        "must_change_password": False,
        "auth_version": 3,
        "failed_login_attempts": 0,
        "locked_until": None,
        "home_market": "BR",
    }
    values.update(overrides)
    return User(**values)


def _result(*, scalar=None, scalars=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = scalars or []
    return result


def test_market_actor_uses_the_role_and_links_of_each_market():
    user = _user()
    br = UserMarket(user_id=user.id, market_code="BR", role="admin", status="active")
    eu_rep = uuid.uuid4()
    eu = UserMarket(
        user_id=user.id,
        market_code="EU",
        role="representante",
        status="active",
        rep_id=eu_rep,
    )
    assert MarketPrincipal(user, MARKETS["BR"], br).actor.role == UserRole.admin
    eu_actor = MarketPrincipal(user, MARKETS["EU"], eu).actor
    assert eu_actor.role == UserRole.representante
    assert eu_actor.rep_id == eu_rep
    assert eu_actor.linked_id is None


def test_platform_token_has_no_market_and_commercial_dependency_rejects_it():
    async def run():
        user = _user()
        token = create_access_token(user.id, None, user.auth_version, None, scope="platform")
        payload = decode_access_token(token)
        assert payload["scope"] == "platform"
        assert "market" not in payload
        with pytest.raises(HTTPException) as exc:
            await get_market_principal(token=token, db=AsyncMock())
        assert exc.value.status_code == 401
    asyncio.run(run())


def test_market_token_is_rejected_by_platform_dependency():
    async def run():
        user = _user()
        token = create_access_token(user.id, "admin", user.auth_version, "BR")
        with pytest.raises(HTTPException) as exc:
            await get_platform_principal(token=token, db=AsyncMock())
        assert exc.value.status_code == 401
    asyncio.run(run())


def test_platform_admin_satisfies_specific_platform_capabilities():
    dependency = require_platform_capability("activate_market")
    principal = PlatformPrincipal(_user(), frozenset({"platform_admin"}))
    assert dependency(principal=principal) is principal
    with pytest.raises(HTTPException) as exc:
        dependency(principal=PlatformPrincipal(_user(), frozenset({"read_outbox"})))
    assert exc.value.status_code == 403


def test_platform_login_does_not_require_a_commercial_market():
    async def run():
        user = _user()
        db = AsyncMock()
        db.execute.side_effect = [
            _result(scalar=user),
            _result(scalar=user.id),
        ]
        response = MagicMock()
        request = SimpleNamespace(state=SimpleNamespace(request_id="test"))
        with patch("app.api.routers.auth.verify_password", return_value=True):
            result = await platform_login.__wrapped__(
                request=request,
                response=response,
                payload=LoginRequest(identifier=user.email, password="secret"),
                db=db,
            )
        payload = decode_access_token(result.access_token)
        assert payload["scope"] == "platform"
        assert "market" not in payload
        stored = db.add.call_args.args[0]
        assert stored.scope == "platform"
        assert stored.active_market is None
    asyncio.run(run())


def test_commercial_login_denies_identity_without_active_market():
    async def run():
        user = _user()
        db = AsyncMock()
        db.execute.side_effect = [_result(scalar=user), _result(scalars=[])]
        request = SimpleNamespace(state=SimpleNamespace(request_id="test"))
        with patch("app.api.routers.auth.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                await login.__wrapped__(
                    request=request,
                    response=MagicMock(),
                    payload=LoginRequest(identifier=user.email, password="secret"),
                    db=db,
                )
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_switch_market_emits_the_target_markets_role():
    async def run():
        user = _user()
        br = UserMarket(user_id=user.id, market_code="BR", role="admin", status="active")
        eu = UserMarket(
            user_id=user.id,
            market_code="EU",
            role="representante",
            status="active",
            rep_id=uuid.uuid4(),
        )
        stored = SimpleNamespace(active_market="BR", scope="market")
        db = AsyncMock()
        db.execute.return_value = _result(scalar=stored)
        with patch("app.api.routers.auth.require_market_access", AsyncMock(return_value=eu)):
            result = await switch_market(
                body=SwitchMarketRequest(market="EU"),
                request=SimpleNamespace(),
                db=db,
                principal=MarketPrincipal(user, MARKETS["BR"], br),
                refresh_token="refresh",
                _origin_guard=None,
            )
        payload = decode_access_token(result.access_token)
        assert payload["market"] == "EU"
        assert payload["role"] == "representante"
        assert stored.active_market == "EU"
    asyncio.run(run())


def test_vat_approval_requires_permission_in_the_active_eu_market():
    async def run():
        user = _user()
        br = UserMarket(
            user_id=user.id,
            market_code="BR",
            role="admin",
            status="active",
            can_approve_tax=True,
        )
        eu_without_permission = UserMarket(
            user_id=user.id,
            market_code="EU",
            role="admin",
            status="active",
            can_approve_tax=False,
        )
        body = VatDecisionRequest(status="approved", vat_rate=23)
        for principal in (
            MarketPrincipal(user, MARKETS["BR"], br),
            MarketPrincipal(user, MARKETS["EU"], eu_without_permission),
        ):
            with pytest.raises(HTTPException) as exc:
                await decide_europe_vat(uuid.uuid4(), body, AsyncMock(), principal)
            assert exc.value.status_code == 403
    asyncio.run(run())
