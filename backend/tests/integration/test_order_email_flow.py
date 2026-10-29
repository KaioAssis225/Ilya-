import base64
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.market import PriceList
from app.models.order import Order
from app.models.order_email import OrderDocument, OrderEmailDelivery
from app.models.user import UserRole
from app.services import order_email as order_email_service
from tests.factories import make_client, make_representative, make_user, make_user_market
from tests.factories.orders import make_order


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


async def _scenario(db: AsyncSession, *, market: str = "BR", same_email: bool = False):
    user = await make_user(
        db,
        email=f"order-email-{uuid.uuid4()}@ilya-test.invalid",
        role=UserRole.admin,
        home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    price_list = (
        await db.execute(
            select(PriceList)
            .where(PriceList.market_code == market, PriceList.code == "lojista")
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()
    client = await make_client(db, price_list, market_code=market, name="Cliente E-mail")
    representative = await make_representative(db, market_code=market, name="Representante E-mail")
    client.email = "client@example.com"
    representative.email = "client@example.com" if same_email else "rep@example.com"
    client.rep_id = representative.id
    order = await make_order(db, client, user.id)
    order.rep_id = representative.id
    token = create_access_token(user.id, "admin", user.auth_version, market)
    await db.flush()
    return order, client, representative, {"Authorization": f"Bearer {token}"}


async def _finalize(client: AsyncClient, order: Order, headers: dict[str, str]):
    return await client.post(
        f"/api/v1/orders/{order.id}/finalize",
        headers=headers,
        json={"pdf_base64": base64.b64encode(PDF).decode()},
    )


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_finalize_persists_immutable_pdf_and_queues_both_recipients(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
    market: str,
):
    monkeypatch.setattr(settings, "ORDER_EMAIL_ENABLED", True)
    persist = AsyncMock()
    monkeypatch.setattr(order_email_service, "persist_order_pdf", persist)
    order, _, _, headers = await _scenario(db_session, market=market)

    response = await _finalize(client, order, headers)

    assert response.status_code == 200
    document = (
        await db_session.execute(select(OrderDocument).where(OrderDocument.order_id == order.id))
    ).scalar_one()
    deliveries = list(
        (
            await db_session.execute(
                select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id)
            )
        ).scalars()
    )
    assert document.sha256
    assert document.content_length == len(PDF)
    assert {row.recipient_kind for row in deliveries} == {"client", "representative"}
    assert {row.status for row in deliveries} == {"pending"}
    persist.assert_awaited_once()


async def test_finalize_deduplicates_equal_client_and_representative_email(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ORDER_EMAIL_ENABLED", True)
    monkeypatch.setattr(order_email_service, "persist_order_pdf", AsyncMock())
    order, _, _, headers = await _scenario(db_session, same_email=True)

    assert (await _finalize(client, order, headers)).status_code == 200
    deliveries = list(
        (
            await db_session.execute(
                select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id)
            )
        ).scalars()
    )
    assert len(deliveries) == 1
    assert deliveries[0].recipient_kind == "client_and_representative"


async def test_missing_client_email_does_not_block_representative(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ORDER_EMAIL_ENABLED", True)
    monkeypatch.setattr(order_email_service, "persist_order_pdf", AsyncMock())
    order, customer, _, headers = await _scenario(db_session)
    customer.email = None
    await db_session.flush()

    assert (await _finalize(client, order, headers)).status_code == 200
    deliveries = list(
        (
            await db_session.execute(
                select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id)
            )
        ).scalars()
    )
    assert {row.status for row in deliveries} == {"pending", "missing_address"}


async def test_pdf_storage_failure_rolls_back_finalization(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ORDER_EMAIL_ENABLED", True)
    monkeypatch.setattr(
        order_email_service,
        "persist_order_pdf",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    order, _, _, headers = await _scenario(db_session)
    order_id = order.id
    await db_session.commit()

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await _finalize(client, order, headers)

    await db_session.rollback()
    db_session.expunge_all()
    stored = (
        await db_session.execute(
            select(Order)
            .where(Order.id == order_id)
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()
    assert stored.is_finalized is False
    assert (
        await db_session.execute(select(OrderDocument).where(OrderDocument.order_id == order_id))
    ).scalar_one_or_none() is None
