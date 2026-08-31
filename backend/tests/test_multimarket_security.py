import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.markets import (
    MARKETS,
    MarketPrincipal,
    build_market_principal,
    allowed_markets,
    require_allowed_market,
)
from app.core.security import create_access_token, decode_access_token
from app.models.client import Client
from app.models.user import UserRole
from app.api.routers.clients import get_client
from app.api.routers.orders import update_order
from app.api.routers.reps import delete_representative, get_representative
from app.schemas.order import OrderUpdate


def _user(role=UserRole.vendedor, home="BR"):
    return SimpleNamespace(id=uuid.uuid4(), role=role, home_market=home)


def test_access_token_signs_market_scope():
    token = create_access_token(uuid.uuid4(), "admin", market="EU")
    assert decode_access_token(token)["market"] == "EU"


def test_market_principal_binds_only_the_validated_market():
    async def run():
        db = AsyncMock()
        db.sync_session = SimpleNamespace(info={})
        with patch("app.core.markets.require_allowed_market", AsyncMock(return_value="EU")):
            principal = await build_market_principal(db, _user(UserRole.admin), "EU")
        assert principal.code == "EU"
        assert principal.market is MARKETS["EU"]
        assert db.sync_session.info == {"active_market": "EU"}

    asyncio.run(run())


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


def test_client_lookup_always_contains_active_market_scope():
    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        user = SimpleNamespace(
            role=UserRole.admin,
            active_market="BR",
            linked_id=None,
            rep_id=None,
        )

        with pytest.raises(HTTPException) as exc:
            await get_client(
                uuid.uuid4(),
                db=db,
                current_user=user,
                principal=MarketPrincipal(user=user, market=MARKETS["BR"]),
            )

        statement = db.execute.await_args.args[0]
        assert "clients.market_code" in str(statement)
        assert "BR" in statement.compile().params.values()
        assert exc.value.status_code == 404

    asyncio.run(run())


def test_representative_lookup_always_contains_active_market_scope():
    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        user = SimpleNamespace(
            role=UserRole.admin,
            active_market="EU",
            linked_id=None,
            rep_id=None,
        )

        with pytest.raises(HTTPException) as exc:
            await get_representative(
                uuid.uuid4(),
                db=db,
                current_user=user,
                principal=MarketPrincipal(user=user, market=MARKETS["EU"]),
            )

        statement = db.execute.await_args.args[0]
        assert "representatives.market_code" in str(statement)
        assert "EU" in statement.compile().params.values()
        assert exc.value.status_code == 404

    asyncio.run(run())


def test_deleting_eu_representative_retires_links_without_breaking_history():
    async def run():
        rep = SimpleNamespace(relationship_ended_at=None)
        linked_user = SimpleNamespace(is_active=True, auth_version=4)
        rep_result = MagicMock()
        rep_result.scalar_one_or_none.return_value = rep
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [linked_user]
        db = AsyncMock()
        db.execute.side_effect = [rep_result, users_result, MagicMock()]
        user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
        principal = MarketPrincipal(user=user, market=MARKETS["EU"])

        await delete_representative(
            uuid.uuid4(),
            db=db,
            current_user=user,
            principal=principal,
        )

        assert rep.relationship_ended_at is not None
        assert linked_user.is_active is False
        assert linked_user.auth_version == 5
        assert "representatives.market_code" in str(db.execute.await_args_list[0].args[0])
        assert "EU" in db.execute.await_args_list[0].args[0].compile().params.values()
        client_unlink = db.execute.await_args_list[2].args[0]
        assert "clients.market_code" in str(client_unlink)
        assert "EU" in client_unlink.compile().params.values()
        db.commit.assert_awaited_once()

    asyncio.run(run())


def test_updating_order_requires_the_active_eu_market_explicitly():
    async def run():
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.return_value = result
        user = SimpleNamespace(
            id=uuid.uuid4(),
            role=UserRole.admin,
            linked_id=None,
            rep_id=None,
        )

        with pytest.raises(HTTPException) as exc:
            await update_order(
                uuid.uuid4(),
                OrderUpdate(notes="Portugal"),
                db=db,
                current_user=user,
                principal=MarketPrincipal(user=user, market=MARKETS["EU"]),
            )

        statement = db.execute.await_args.args[0]
        assert "orders.market_code" in str(statement)
        assert "EU" in statement.compile().params.values()
        assert exc.value.status_code == 404

    asyncio.run(run())


def test_orm_market_scope_does_not_reuse_previous_market():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE clients (id CHAR(32) PRIMARY KEY, market_code VARCHAR(2) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO clients (id, market_code) VALUES "
            "('00000000000000000000000000000001', 'BR'), "
            "('00000000000000000000000000000002', 'EU')"
        ))

    with Session(engine) as session:
        count_query = select(func.count()).select_from(Client)
        session.info["active_market"] = "BR"
        assert session.execute(count_query).scalar_one() == 1
        session.info["active_market"] = "EU"
        assert session.execute(count_query).scalar_one() == 1
