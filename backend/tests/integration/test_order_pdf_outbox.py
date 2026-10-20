import uuid
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_user, make_user_market, make_client
from tests.factories.orders import make_order
from app.models.market import PriceList
from app.models.order import Order
from app.models.moloni import MoloniExportJob
from app.api.routers import orders as orders_router
from app.services.moloni_jobs import enqueue_finalized_eu_order
from app.core.security import create_access_token
from app.models.user import UserRole

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _setup_eu_order(db_session: AsyncSession):
    market = "EU"
    user = await make_user(
        db_session,
        email=f"unique-{uuid.uuid4()}@ilya-test.invalid",
        role=UserRole.admin,
        home_market=market,
    )
    await make_user_market(db_session, user, market_code=market, role="admin")
    price_list = (
        await db_session.execute(
            select(PriceList)
            .where(PriceList.market_code == market, PriceList.code == "lojista")
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()
    client_obj = await make_client(db_session, price_list, market_code=market, name="EU Client")
    order = await make_order(db_session, client_obj, user.id)
    token = create_access_token(user.id, "admin", user.auth_version, market)
    return order, token


async def _setup_br_order(db_session: AsyncSession):
    market = "BR"
    user = await make_user(
        db_session,
        email=f"unique-{uuid.uuid4()}@ilya-test.invalid",
        role=UserRole.admin,
        home_market=market,
    )
    await make_user_market(db_session, user, market_code=market, role="admin")
    price_list = (
        await db_session.execute(
            select(PriceList)
            .where(PriceList.market_code == market, PriceList.code == "lojista")
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()
    client_obj = await make_client(db_session, price_list, market_code=market, name="BR Client")
    order = await make_order(db_session, client_obj, user.id)
    token = create_access_token(user.id, "admin", user.auth_version, market)
    return order, token


async def test_eu_finalization_creates_job(client: AsyncClient, db_session: AsyncSession):
    order, token = await _setup_eu_order(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(f"/api/v1/orders/{order.id}/finalize", json={}, headers=headers)
    assert resp.status_code == 200
    await db_session.refresh(order)
    assert order.is_finalized is True
    jobs = (
        await db_session.execute(
            select(MoloniExportJob)
            .where(MoloniExportJob.order_id == order.id)
            .execution_options(skip_market_scope=True)
        )
    ).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == "pending"
    assert jobs[0].attempts == 0


async def test_br_finalization_no_job(client: AsyncClient, db_session: AsyncSession):
    order, token = await _setup_br_order(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(f"/api/v1/orders/{order.id}/finalize", json={}, headers=headers)
    assert resp.status_code == 200
    await db_session.refresh(order)
    assert order.is_finalized is True
    jobs = (
        await db_session.execute(
            select(MoloniExportJob)
            .where(MoloniExportJob.order_id == order.id)
            .execution_options(skip_market_scope=True)
        )
    ).scalars().all()
    assert len(jobs) == 0


async def test_duplicate_direct_enqueue_does_nothing(db_session: AsyncSession):
    order, _ = await _setup_eu_order(db_session)
    await enqueue_finalized_eu_order(db_session, order.id)
    await enqueue_finalized_eu_order(db_session, order.id)
    jobs = (
        await db_session.execute(
            select(MoloniExportJob)
            .where(MoloniExportJob.order_id == order.id)
            .execution_options(skip_market_scope=True)
        )
    ).scalars().all()
    assert len(jobs) == 1


async def test_finalize_failure_rolls_back(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    order, token = await _setup_eu_order(db_session)
    order_id = order.id
    await db_session.commit()

    async def async_boom(db, order_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(orders_router, "enqueue_finalized_eu_order", async_boom)
    headers = {"Authorization": f"Bearer {token}"}
    with pytest.raises(RuntimeError):
        await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=headers)

    await db_session.rollback()
    db_session.expunge_all()
    order_after = (
        await db_session.execute(
            select(Order)
            .where(Order.id == order_id)
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()
    assert order_after.is_finalized is False
    jobs = (
        await db_session.execute(
            select(MoloniExportJob)
            .where(MoloniExportJob.order_id == order_id)
            .execution_options(skip_market_scope=True)
        )
    ).scalars().all()
    assert len(jobs) == 0


async def test_iso33_dashboard_isolation(client: AsyncClient, db_session: AsyncSession):
    eu_order, eu_token = await _setup_eu_order(db_session)
    br_order, br_token = await _setup_br_order(db_session)

    eu_order.total_with_ipi = Decimal("100.00")
    eu_order.total_value = Decimal("90.00")
    br_order.total_with_ipi = Decimal("200.00")
    br_order.total_value = Decimal("180.00")
    await db_session.commit()

    eu_headers = {"Authorization": f"Bearer {eu_token}"}
    br_headers = {"Authorization": f"Bearer {br_token}"}

    eu_resp = await client.get("/api/v1/dashboard/overview", headers=eu_headers)
    br_resp = await client.get("/api/v1/dashboard/overview", headers=br_headers)
    assert eu_resp.status_code == 200
    assert br_resp.status_code == 200

    eu_data = eu_resp.json()
    br_data = br_resp.json()

    assert eu_data["metrics"]["orders_total"] == 1
    assert eu_data["metrics"]["revenue_total"] == 100.0
    assert br_data["metrics"]["orders_total"] == 1
    assert br_data["metrics"]["revenue_total"] == 200.0

    eu_chart_total = sum(item["revenue"] for item in eu_data["chart"])
    br_chart_total = sum(item["revenue"] for item in br_data["chart"])
    assert eu_chart_total == 100.0
    assert br_chart_total == 200.0

    eu_rep_orders = sum(rep["orders"] for rep in eu_data["representatives"])
    eu_rep_revenue = sum(rep["revenue"] for rep in eu_data["representatives"])
    br_rep_orders = sum(rep["orders"] for rep in br_data["representatives"])
    br_rep_revenue = sum(rep["revenue"] for rep in br_data["representatives"])
    assert eu_rep_orders == 1
    assert eu_rep_revenue == 100.0
    assert br_rep_orders == 1
    assert br_rep_revenue == 200.0

    assert all(rep["name"] != "Sem representante" or rep["orders"] == 1 for rep in eu_data["representatives"])
    assert all(rep["name"] != "Sem representante" or rep["orders"] == 1 for rep in br_data["representatives"])