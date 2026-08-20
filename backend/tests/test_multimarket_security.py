import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.markets import active_market_for, allowed_markets, require_allowed_market
from app.core.security import create_access_token, decode_access_token
from app.models.user import UserRole


def _user(role=UserRole.vendedor, home="BR"):
    return SimpleNamespace(id=uuid.uuid4(), role=role, home_market=home)


def test_access_token_signs_market_scope():
    token = create_access_token(uuid.uuid4(), "admin", market="EU")
    assert decode_access_token(token)["market"] == "EU"


def test_legacy_helper_defaults_to_br_without_ip_or_header():
    assert active_market_for(SimpleNamespace()) == "BR"


def test_admin_receives_both_markets_only_when_europe_flag_enabled():
    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = ["BR", "EU"]
        db.execute.return_value = result
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", True):
            assert await allowed_markets(db, _user(UserRole.admin)) == ["BR", "EU"]
    asyncio.run(run())


def test_non_admin_cannot_switch_to_unlinked_market():
    async def run():
        db = AsyncMock()
        links = MagicMock(); links.scalars.return_value.all.return_value = ["BR"]
        enabled = MagicMock(); enabled.scalars.return_value.all.return_value = ["BR"]
        db.execute.side_effect = [links, enabled]
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", True):
            with pytest.raises(HTTPException) as exc:
                await require_allowed_market(db, _user(), "EU")
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_feature_flag_blocks_europe_even_for_admin():
    async def run():
        db = AsyncMock()
        result = MagicMock(); result.scalars.return_value.all.return_value = ["BR"]
        db.execute.return_value = result
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", False):
            with pytest.raises(HTTPException) as exc:
                await require_allowed_market(db, _user(UserRole.admin), "EU")
        assert exc.value.status_code == 403
    asyncio.run(run())
