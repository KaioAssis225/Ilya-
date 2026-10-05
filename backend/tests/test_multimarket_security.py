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
    require_market_access,
    require_launch_country,
)
from app.core.security import create_access_token, decode_access_token
from app.models.client import Client
from app.models.order import Order
from app.models.product import Product
from app.models.user import UserRole
from app.api.routers.clients import get_client
from app.api.routers.orders import _load_products_and_types, update_order
from app.api.routers.reps import delete_representative, get_representative
from app.schemas.order import OrderUpdate


def _user(role=UserRole.vendedor, home="BR"):
    return SimpleNamespace(id=uuid.uuid4(), role=role, home_market=home)


def test_access_token_signs_market_scope():
    token = create_access_token(uuid.uuid4(), "admin", market="EU")
    assert decode_access_token(token)["market"] == "EU"
    assert decode_access_token(token)["scope"] == "market"


def test_market_principal_binds_only_the_validated_market():
    async def run():
        db = AsyncMock()
        db.sync_session = SimpleNamespace(info={})
        access = SimpleNamespace(market_code="EU", role="admin")
        with patch("app.core.markets.require_market_access", AsyncMock(return_value=access)):
            principal = await build_market_principal(db, _user(UserRole.admin), "EU")
        assert principal.code == "EU"
        assert principal.market is MARKETS["EU"]
        assert db.sync_session.info == {"active_market": "EU"}

    asyncio.run(run())


def test_global_admin_without_active_user_market_receives_no_market():
    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", True):
            assert await allowed_markets(db, _user(UserRole.admin)) == []
    asyncio.run(run())


def test_non_admin_cannot_switch_to_unlinked_market():
    async def run():
        db = AsyncMock()
        links = MagicMock()
        links.scalars.return_value.all.return_value = [SimpleNamespace(market_code="BR")]
        db.execute.return_value = links
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", True):
            with pytest.raises(HTTPException) as exc:
                await require_allowed_market(db, _user(), "EU")
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_feature_flag_blocks_europe_even_for_admin():
    async def run():
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [SimpleNamespace(market_code="EU")]
        db.execute.return_value = result
        with patch("app.core.markets.settings.EUROPE_MARKET_ENABLED", False):
            with pytest.raises(HTTPException) as exc:
                await require_allowed_market(db, _user(UserRole.admin), "EU")
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_primeira_liberacao_eu_aceita_somente_portugal():
    assert require_launch_country("EU", " pt ") == "PT"
    assert require_launch_country("BR", "PT") == "BR"
    with pytest.raises(HTTPException) as exc:
        require_launch_country("EU", "ES")
    assert exc.value.status_code == 422


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
        linked_access = SimpleNamespace(user_id=uuid.uuid4(), status="active")
        rep_result = MagicMock()
        rep_result.scalar_one_or_none.return_value = rep
        access_result = MagicMock()
        access_result.scalars.return_value.all.return_value = [linked_access]
        db = AsyncMock()
        db.execute.side_effect = [rep_result, access_result, MagicMock(), MagicMock()]
        user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
        principal = MarketPrincipal(user=user, market=MARKETS["EU"])

        await delete_representative(
            uuid.uuid4(),
            db=db,
            current_user=user,
            principal=principal,
        )

        assert rep.relationship_ended_at is not None
        assert linked_access.status == "suspended"
        assert "representatives.market_code" in str(db.execute.await_args_list[0].args[0])
        assert "EU" in db.execute.await_args_list[0].args[0].compile().params.values()
        commercial_refresh_revoke = db.execute.await_args_list[2].args[0]
        assert "refresh_tokens.scope" in str(commercial_refresh_revoke)
        assert "market" in commercial_refresh_revoke.compile().params.values()
        client_unlink = db.execute.await_args_list[3].args[0]
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


def test_order_product_lookup_contains_market_even_without_listener():
    async def run():
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute.return_value = result

        products, types = await _load_products_and_types(db, ["EU-1"], "EU")

        statement = db.execute.await_args.args[0]
        assert "products.market_code" in str(statement)
        assert "EU" in statement.compile().params.values()
        assert products == {}
        assert types == {}

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
        connection.execute(text(
            "CREATE TABLE products (id CHAR(32) PRIMARY KEY, market_code VARCHAR(2) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO products (id, market_code) VALUES "
            "('00000000000000000000000000000003', 'BR'), "
            "('00000000000000000000000000000004', 'EU')"
        ))

    with Session(engine) as session:
        count_query = select(func.count()).select_from(Client)
        product_count_query = select(func.count()).select_from(Product)
        session.info["active_market"] = "BR"
        assert session.execute(count_query).scalar_one() == 1
        assert session.execute(product_count_query).scalar_one() == 1
        session.info["active_market"] = "EU"
        assert session.execute(count_query).scalar_one() == 1
        assert session.execute(product_count_query).scalar_one() == 1


def test_order_lookup_by_id_is_scoped_even_without_explicit_filter():
    """GET e DELETE de pedido consultam `select(Order).where(Order.id == ...)`
    sem mercado explícito (`orders.py:1104,1148`); quem isola é o listener, pelo
    `active_market` que o `MarketPrincipal` grava na sessão. Este teste prova
    que um id conhecido de outro mercado não é materializado (IDOR)."""
    engine = create_engine("sqlite:///:memory:")
    # Order.id e tipado como UUID; o dialeto SQLite o armazena como hex de 32
    # caracteres, entao a comparacao precisa do objeto uuid.UUID, nao da string.
    br_id = uuid.UUID("00000000-0000-0000-0000-000000000011")
    eu_id = uuid.UUID("00000000-0000-0000-0000-000000000012")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE orders (id CHAR(32) PRIMARY KEY, market_code VARCHAR(2) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO orders (id, market_code) VALUES "
            f"('{br_id.hex}', 'BR'), ('{eu_id.hex}', 'EU')"
        ))

    with Session(engine) as session:
        # Sessão BR não alcança o pedido EU, mesmo com o id em mãos.
        session.info["active_market"] = "BR"
        assert session.execute(
            select(func.count()).select_from(Order).where(Order.id == eu_id)
        ).scalar_one() == 0
        assert session.execute(
            select(func.count()).select_from(Order).where(Order.id == br_id)
        ).scalar_one() == 1

        # E o inverso, provando que o critério não ficou preso ao primeiro
        # mercado compilado.
        session.info["active_market"] = "EU"
        assert session.execute(
            select(func.count()).select_from(Order).where(Order.id == br_id)
        ).scalar_one() == 0
        assert session.execute(
            select(func.count()).select_from(Order).where(Order.id == eu_id)
        ).scalar_one() == 1
