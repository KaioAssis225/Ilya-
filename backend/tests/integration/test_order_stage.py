"""Etapa do pedido finalizado (Produção → Entregue): ciclo, RBAC e isolamento."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.order import Order
from app.models.order_history import OrderHistory
from app.models.user import UserRole
from tests.factories.orders import make_order
from tests.factories import make_client, make_representative, make_user, make_user_market
from tests.integration.test_order_lifecycle import (
    _admin,
    _auth,
    _cancel_order,
    _create_client,
    _create_product_with_price,
    _finalize_order,
    _post_order,
    _price_list,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _token(
    db: AsyncSession,
    role: UserRole,
    market: str = "BR",
    *,
    rep_id: uuid.UUID | None = None,
    linked_client_id: uuid.UUID | None = None,
) -> str:
    user = await make_user(
        db,
        email=f"stage-{role.value}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=role,
        home_market=market,
    )
    if linked_client_id is not None:
        user.linked_id = linked_client_id
    await make_user_market(
        db, user, market_code=market, role=role.value,
        rep_id=rep_id, linked_client_id=linked_client_id,
    )
    await db.flush()
    return create_access_token(user.id, role.value, user.auth_version, market)


async def _change_stage(client: AsyncClient, token: str, order_id, stage: str):
    return await client.post(
        f"/api/v1/orders/{order_id}/stage",
        json={"stage": stage},
        headers=_auth(token),
    )


async def _finalized_order(
    client: AsyncClient,
    db: AsyncSession,
    market: str = "BR",
    *,
    client_id: uuid.UUID | None = None,
):
    """Admin cria e finaliza um pedido; devolve (admin, order_id, client_id)."""
    admin = await _admin(db, market)
    price_list = await _price_list(db, market, "lojista")
    product = await _create_product_with_price(db, market, price_list, Decimal("100.00"))
    if client_id is None:
        client_id = await _create_client(db, market, price_list)
    await db.commit()
    created = await _post_order(
        client, admin, client_id, [{"product_code": product.product_code, "qty": 1}]
    )
    assert created.status_code == 201, created.text
    order_id = uuid.UUID(created.json()["id"])
    finalized = await _finalize_order(client, admin, order_id)
    assert finalized.status_code == 200, finalized.text
    return admin, order_id, client_id


async def _order_row(db: AsyncSession, order_id: uuid.UUID) -> Order:
    return (
        await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .execution_options(populate_existing=True, skip_market_scope=True)
        )
    ).scalar_one()


async def test_finalize_places_order_in_production(client, db_session):
    admin, order_id, _ = await _finalized_order(client, db_session)

    order = await _order_row(db_session, order_id)
    assert order.is_finalized is True
    assert order.order_stage == "production"
    assert order.production_started_at == order.finalized_at
    assert order.delivered_at is None

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=_auth(admin.token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["order_stage"] == "production"
    assert detail.json()["delivered_at"] is None


async def test_quote_has_no_stage_until_finalized(client, db_session):
    admin = await _admin(db_session, "BR")
    price_list = await _price_list(db_session, "BR", "lojista")
    product = await _create_product_with_price(db_session, "BR", price_list, Decimal("100.00"))
    client_id = await _create_client(db_session, "BR", price_list)
    created = await _post_order(
        client, admin, client_id, [{"product_code": product.product_code, "qty": 1}]
    )
    assert created.status_code == 201, created.text
    assert created.json()["order_stage"] is None


async def test_mark_delivered_and_back_records_history(client, db_session):
    admin, order_id, _ = await _finalized_order(client, db_session)
    before = await _order_row(db_session, order_id)
    source_version, document_version = before.source_version, before.document_version

    delivered = await _change_stage(client, admin.token, order_id, "delivered")
    assert delivered.status_code == 200, delivered.text
    body = delivered.json()
    assert body["order_stage"] == "delivered"
    assert body["delivered_at"] is not None
    assert body["is_finalized"] is True

    order = await _order_row(db_session, order_id)
    assert order.source_version == source_version + 1
    # O documento (PDF/snapshot) não muda com a etapa.
    assert order.document_version == document_version

    back = await _change_stage(client, admin.token, order_id, "production")
    assert back.status_code == 200, back.text
    assert back.json()["order_stage"] == "production"
    assert back.json()["delivered_at"] is None

    history = (
        await db_session.execute(
            select(OrderHistory)
            .where(OrderHistory.order_id == order_id, OrderHistory.action == "stage_changed")
            .order_by(OrderHistory.created_at, OrderHistory.id)
        )
    ).scalars().all()
    assert sorted(entry.details for entry in history) == [
        "delivered -> production",
        "production -> delivered",
    ]
    assert {entry.user_id for entry in history} == {admin.user_id}


async def test_same_stage_is_idempotent_without_history(client, db_session):
    admin, order_id, _ = await _finalized_order(client, db_session)
    before = await _order_row(db_session, order_id)

    again = await _change_stage(client, admin.token, order_id, "production")
    assert again.status_code == 200, again.text
    assert again.json()["order_stage"] == "production"

    after = await _order_row(db_session, order_id)
    assert after.source_version == before.source_version
    entries = (
        await db_session.execute(
            select(OrderHistory).where(
                OrderHistory.order_id == order_id, OrderHistory.action == "stage_changed"
            )
        )
    ).scalars().all()
    assert entries == []


async def test_list_filters_by_stage(client, db_session):
    admin, delivered_id, client_id = await _finalized_order(client, db_session)
    price_list = await _price_list(db_session, "BR", "lojista")
    product = await _create_product_with_price(db_session, "BR", price_list, Decimal("90.00"))
    await db_session.commit()
    second = await _post_order(
        client, admin, client_id, [{"product_code": product.product_code, "qty": 1}]
    )
    production_id = second.json()["id"]
    assert (await _finalize_order(client, admin, uuid.UUID(production_id))).status_code == 200
    assert (await _change_stage(client, admin.token, delivered_id, "delivered")).status_code == 200

    async def listed(query: str) -> dict[str, dict]:
        response = await client.get(f"/api/v1/orders?limit=100&{query}", headers=_auth(admin.token))
        assert response.status_code == 200, response.text
        return {row["id"]: row for row in response.json()}

    assert set(await listed("stage=delivered")) == {str(delivered_id)}
    assert set(await listed("stage=production")) == {production_id}
    both = await listed("status=finalized")
    assert set(both) == {str(delivered_id), production_id}
    assert both[str(delivered_id)]["order_stage"] == "delivered"
    assert both[str(delivered_id)]["delivered_at"] is not None
    assert both[production_id]["order_stage"] == "production"

    invalid = await client.get("/api/v1/orders?stage=lost", headers=_auth(admin.token))
    assert invalid.status_code == 422


async def test_stage_requires_finalized_and_not_cancelled(client, db_session):
    admin = await _admin(db_session, "BR")
    price_list = await _price_list(db_session, "BR", "lojista")
    product = await _create_product_with_price(db_session, "BR", price_list, Decimal("100.00"))
    client_id = await _create_client(db_session, "BR", price_list)
    items = [{"product_code": product.product_code, "qty": 1}]

    open_order = (await _post_order(client, admin, client_id, items)).json()["id"]
    cancelled = (await _post_order(client, admin, client_id, items)).json()["id"]
    assert (await _cancel_order(client, admin, uuid.UUID(cancelled))).status_code == 200

    for order_id in (open_order, cancelled):
        response = await _change_stage(client, admin.token, order_id, "delivered")
        assert response.status_code == 409, response.text
        assert (await _order_row(db_session, uuid.UUID(order_id))).order_stage is None


async def test_invalid_stage_and_unknown_order(client, db_session):
    admin, order_id, _ = await _finalized_order(client, db_session)

    invalid = await _change_stage(client, admin.token, order_id, "shipped")
    assert invalid.status_code == 422, invalid.text

    unknown = await _change_stage(client, admin.token, uuid.uuid4(), "delivered")
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["detail"] == "Pedido não encontrado."


async def test_final_client_never_changes_stage(client, db_session):
    _, order_id, client_id = await _finalized_order(client, db_session)
    client_token = await _token(db_session, UserRole.cliente, linked_client_id=client_id)
    await db_session.commit()

    # Dono do pedido e pedido inexistente recebem a mesma negativa de papel.
    own = await _change_stage(client, client_token, order_id, "delivered")
    missing = await _change_stage(client, client_token, uuid.uuid4(), "delivered")
    assert own.status_code == missing.status_code == 403
    assert own.json() == missing.json()

    # O cliente continua vendo a própria etapa.
    detail = await client.get(f"/api/v1/orders/{order_id}", headers=_auth(client_token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["order_stage"] == "production"
    assert (await _order_row(db_session, order_id)).order_stage == "production"


async def test_representative_limited_to_own_portfolio(client, db_session):
    price_list = await _price_list(db_session, "BR", "lojista")
    rep_a = await make_representative(db_session, market_code="BR", name="Rep A etapa")
    rep_b = await make_representative(db_session, market_code="BR", name="Rep B etapa")
    client_a = await make_client(db_session, price_list, market_code="BR", name="Cliente A etapa")
    client_b = await make_client(db_session, price_list, market_code="BR", name="Cliente B etapa")
    client_a.rep_id = rep_a.id
    client_b.rep_id = rep_b.id
    await db_session.commit()

    _, order_a, _ = await _finalized_order(client, db_session, client_id=client_a.id)
    _, order_b, _ = await _finalized_order(client, db_session, client_id=client_b.id)
    for order_id, rep in ((order_a, rep_a), (order_b, rep_b)):
        (await _order_row(db_session, order_id)).rep_id = rep.id
    rep_token = await _token(db_session, UserRole.representante, rep_id=rep_a.id)
    await db_session.commit()

    foreign = await _change_stage(client, rep_token, order_b, "delivered")
    missing = await _change_stage(client, rep_token, uuid.uuid4(), "delivered")
    # Pedido de outra carteira é indistinguível de pedido inexistente.
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert (await _order_row(db_session, order_b)).order_stage == "production"

    own = await _change_stage(client, rep_token, order_a, "delivered")
    assert own.status_code == 200, own.text
    assert own.json()["order_stage"] == "delivered"


async def test_products_role_can_change_stage(client, db_session):
    _, order_id, _ = await _finalized_order(client, db_session)
    token = await _token(db_session, UserRole.produtos)
    await db_session.commit()

    response = await _change_stage(client, token, order_id, "delivered")
    assert response.status_code == 200, response.text
    assert response.json()["order_stage"] == "delivered"


async def test_other_market_cannot_see_or_change_stage(client, db_session):
    _, order_id, _ = await _finalized_order(client, db_session, "BR")
    eu_admin = await _admin(db_session, "EU")
    await db_session.commit()

    response = await _change_stage(client, eu_admin.token, order_id, "delivered")
    assert response.status_code == 404, response.text
    assert (await _order_row(db_session, order_id)).order_stage == "production"


async def test_eu_order_follows_the_same_cycle(client, db_session):
    # Pedido EU montado direto no banco: o fluxo de criação europeu exige IVA
    # aprovado por produto, irrelevante para o que este teste cobre.
    admin = await _admin(db_session, "EU")
    price_list = await _price_list(db_session, "EU", "lojista")
    eu_client = await make_client(db_session, price_list, market_code="EU", name="Cliente EU etapa")
    order = await make_order(db_session, eu_client, admin.user_id)
    order.is_finalized = True
    order.finalized_at = order.production_started_at = datetime.now(timezone.utc)
    order.order_stage = "production"
    await db_session.commit()

    response = await _change_stage(client, admin.token, order.id, "delivered")
    assert response.status_code == 200, response.text
    assert response.json()["order_stage"] == "delivered"
    assert response.json()["market_code"] == "EU"


async def test_stage_endpoint_is_rate_limited(client, db_session):
    admin, order_id, _ = await _finalized_order(client, db_session)

    statuses = [
        (await _change_stage(client, admin.token, order_id, "production")).status_code
        for _ in range(31)
    ]
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429


async def test_database_rejects_inconsistent_stage(client, db_session):
    _, order_id, client_id = await _finalized_order(client, db_session)
    admin = await _admin(db_session, "BR")
    price_list = await _price_list(db_session, "BR", "lojista")
    product = await _create_product_with_price(db_session, "BR", price_list, Decimal("100.00"))
    created = await _post_order(
        client, admin, client_id, [{"product_code": product.product_code, "qty": 1}]
    )
    quote_id = uuid.UUID(created.json()["id"])
    await db_session.commit()

    async def rejected(sql: str, **params) -> str:
        with pytest.raises(IntegrityError) as caught:
            async with db_session.begin_nested():
                await db_session.execute(text(sql), params)
        return str(caught.value)

    assert "ck_orders_stage_valid" in await rejected(
        "UPDATE orders SET order_stage = 'shipped' WHERE id = :id", id=order_id
    )
    # Entregue exige a data de entrega.
    assert "ck_orders_stage_delivered_at" in await rejected(
        "UPDATE orders SET order_stage = 'delivered' WHERE id = :id", id=order_id
    )
    # Produção não carrega data de entrega.
    assert "ck_orders_stage_delivered_at" in await rejected(
        "UPDATE orders SET delivered_at = now() WHERE id = :id", id=order_id
    )
    # Só pedido finalizado tem etapa.
    assert "ck_orders_stage_requires_finalized" in await rejected(
        "UPDATE orders SET order_stage = 'production' WHERE id = :id", id=quote_id
    )
