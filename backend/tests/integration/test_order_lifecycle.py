import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.client import Client
from app.models.market import PriceList, ProductPrice
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import (
    make_client,
    make_product,
    make_product_group,
    make_product_market,
    make_product_price,
    make_representative,
    make_product_type,
    make_user,
    make_user_market,
)

from tests.factories.orders import make_order

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP_SCOPE = {"skip_market_scope": True}


@dataclass(frozen=True)
class Admin:
    token: str
    user_id: uuid.UUID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _admin(db: AsyncSession, market: str) -> Admin:
    user = await make_user(
        db,
        email=f"order-{market.lower()}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.admin,
        home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    return Admin(create_access_token(user.id, "admin", user.auth_version, market), user.id)


async def _price_list(db: AsyncSession, market: str, code: str) -> PriceList:
    return (
        await db.execute(
            select(PriceList)
            .where(PriceList.market_code == market, PriceList.code == code)
            .execution_options(**_SKIP_SCOPE)
        )
    ).scalar_one()


async def _create_product_with_price(
    db: AsyncSession,
    market: str,
    price_list: PriceList,
    amount: Decimal,
    *,
    description: str = "Mesa sintética",
    product_code: str | None = None,
) -> Product:
    suffix = uuid.uuid4().hex[:8].upper()
    group = await make_product_group(db, market_code=market, name=f"P08a grupo {suffix}", ipi=Decimal("0"))
    product_type = await make_product_type(db, market_code=market, name=f"P08a tipo {suffix}", group=group)
    product = await make_product(
        db,
        market_code=market,
        product_code=product_code or f"TST-{market}-{suffix}",
        description=description,
    )
    product.type = product_type.name
    await make_product_market(db, product)
    await make_product_price(db, product, price_list, amount=amount)
    await db.flush()
    return product


async def _create_client(db: AsyncSession, market: str, price_list: PriceList) -> uuid.UUID:
    client = await make_client(
        db,
        price_list,
        market_code=market,
        name=f"Cliente {uuid.uuid4().hex[:6]}",
    )
    await db.flush()
    return client.id


async def _post_order(
    client: AsyncClient,
    admin: Admin,
    client_id: uuid.UUID,
    items: list[dict],
):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(client_id), "items": items},
        headers=_auth(admin.token),
    )


async def _put_order(
    client: AsyncClient,
    admin: Admin,
    order_id: uuid.UUID,
    items: list[dict],
):
    return await client.put(
        f"/api/v1/orders/{order_id}",
        json={"items": items},
        headers=_auth(admin.token),
    )


async def _finalize_order(client: AsyncClient, admin: Admin, order_id: uuid.UUID):
    return await client.post(
        f"/api/v1/orders/{order_id}/finalize",
        json={},
        headers=_auth(admin.token),
    )


async def _cancel_order(client: AsyncClient, admin: Admin, order_id: uuid.UUID):
    return await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={},
        headers=_auth(admin.token),
    )


async def _capture_item_snapshot(db: AsyncSession, order_id: uuid.UUID) -> tuple:
    row = (
        await db.execute(
            select(OrderItem.description, OrderItem.unit_price, OrderItem.qty).where(
                OrderItem.order_id == order_id
            )
        )
    ).one()
    return row


async def _capture_history_json(db: AsyncSession, order_id: uuid.UUID) -> list[dict]:
    histories = (
        await db.execute(
            select(OrderHistory)
            .where(OrderHistory.order_id == order_id)
            .order_by(OrderHistory.created_at)
        )
    ).scalars().all()
    return [h.items_snapshot for h in histories]


async def _capture_history_actions(db: AsyncSession, order_id: uuid.UUID) -> list[str]:
    histories = (
        await db.execute(
            select(OrderHistory)
            .where(OrderHistory.order_id == order_id)
            .order_by(OrderHistory.created_at)
        )
    ).scalars().all()
    return [h.action for h in histories]


async def test_a_order_lifecycle_br(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(db_session, "BR")
    pl_lojista = await _price_list(db_session, "BR", "lojista")

    product = await _create_product_with_price(
        db_session, "BR", pl_lojista, Decimal("100.00"), description="Descrição original"
    )
    original_description = product.description
    original_price = Decimal("100.00")
    product_code = product.product_code

    client_id = await _create_client(db_session, "BR", pl_lojista)

    resp = await _post_order(
        client,
        admin,
        client_id,
        [{"product_code": product_code, "qty": 1}],
    )
    assert resp.status_code == 201, resp.text
    order_data = resp.json()
    order_id = uuid.UUID(order_data["id"])

    captured_item = await _capture_item_snapshot(db_session, order_id)
    assert captured_item == (original_description, Decimal("100.00"), 1)
    captured_history_json = await _capture_history_json(db_session, order_id)
    captured_history_actions = await _capture_history_actions(db_session, order_id)
    assert captured_history_actions == ["created"]

    edit_resp = await _put_order(
        client,
        admin,
        order_id,
        [{"product_code": product_code, "qty": 2}],
    )
    assert edit_resp.status_code == 200, edit_resp.text

    item_after_edit = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalar_one()
    assert item_after_edit.description == original_description
    assert item_after_edit.qty == 2
    assert item_after_edit.unit_price == original_price
    assert item_after_edit.ipi_value is not None

    order_after_edit = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    assert order_after_edit.total_value == Decimal("200.00")
    assert order_after_edit.price_list_code == "lojista"
    assert order_after_edit.is_finalized is False
    assert order_after_edit.is_cancelled is False

    history_after_edit_json = await _capture_history_json(db_session, order_id)
    history_after_edit_actions = await _capture_history_actions(db_session, order_id)
    assert history_after_edit_actions == ["created", "edited"]
    assert history_after_edit_json[0] == captured_history_json[0]

    finalize_resp = await _finalize_order(client, admin, order_id)
    assert finalize_resp.status_code == 200, finalize_resp.text

    item_after_final = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalar_one()
    captured_item_after_final = (
        item_after_final.description,
        item_after_final.unit_price,
        item_after_final.qty,
    )

    order_after_final = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    captured_order_after_final = (
        order_after_final.total_value,
        order_after_final.price_list_code,
        order_after_final.is_finalized,
        order_after_final.is_cancelled,
    )
    assert order_after_final.is_finalized is True
    assert order_after_final.is_cancelled is False

    history_after_final_json = await _capture_history_json(db_session, order_id)
    history_after_final_actions = await _capture_history_actions(db_session, order_id)
    assert history_after_final_actions == ["created", "edited", "finalized"]

    product.description = "Nova descrição"
    price = (
        await db_session.execute(
            select(ProductPrice).where(
                ProductPrice.product_id == product.id,
                ProductPrice.price_list_id == pl_lojista.id,
            )
        )
    ).scalar_one()
    price.amount = Decimal("150.00")
    await db_session.commit()

    db_session.expire_all()

    item_after_change = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalar_one()
    assert (
        item_after_change.description,
        item_after_change.unit_price,
        item_after_change.qty,
    ) == captured_item_after_final

    order_after_change = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    assert (
        order_after_change.total_value,
        order_after_change.price_list_code,
        order_after_change.is_finalized,
        order_after_change.is_cancelled,
    ) == captured_order_after_final

    history_after_change_json = await _capture_history_json(db_session, order_id)
    history_after_change_actions = await _capture_history_actions(db_session, order_id)
    assert history_after_change_actions == history_after_final_actions
    assert history_after_change_json == history_after_final_json

    re_edit = await _put_order(
        client,
        admin,
        order_id,
        [{"product_code": product_code, "qty": 1}],
    )
    assert re_edit.status_code == 409, re_edit.text

    re_cancel = await _cancel_order(client, admin, order_id)
    assert re_cancel.status_code == 409, re_cancel.text

    re_finalize = await _finalize_order(client, admin, order_id)
    assert re_finalize.status_code == 409, re_finalize.text


async def test_b_iso25_client_price_list_change(client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(db_session, "BR")
    pl_lojista = await _price_list(db_session, "BR", "lojista")
    pl_corporativo = await _price_list(db_session, "BR", "corporativo")

    product = await _create_product_with_price(
        db_session, "BR", pl_lojista, Decimal("100.00"), description="Produto ISO-25"
    )
    await make_product_price(db_session, product, pl_corporativo, amount=Decimal("200.00"))
    await db_session.flush()

    client_id = await _create_client(db_session, "BR", pl_lojista)

    resp = await _post_order(
        client,
        admin,
        client_id,
        [{"product_code": product.product_code, "qty": 1}],
    )
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["id"])

    captured_item = await _capture_item_snapshot(db_session, order_id)
    assert captured_item == ("Produto ISO-25", Decimal("100.00"), 1)

    captured_history_json = await _capture_history_json(db_session, order_id)
    captured_history_actions = await _capture_history_actions(db_session, order_id)
    assert captured_history_actions == ["created"]

    client_obj = (
        await db_session.execute(select(Client).where(Client.id == client_id))
    ).scalar_one()
    client_obj.price_list_id = pl_corporativo.id
    client_obj.price_profile = "corporativo"
    await db_session.commit()

    edit_resp = await _put_order(
        client,
        admin,
        order_id,
        [{"product_code": product.product_code, "qty": 2}],
    )
    assert edit_resp.status_code == 200, edit_resp.text

    order_after_edit = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    assert order_after_edit.price_list_code == "lojista"
    assert order_after_edit.total_value == Decimal("200.00")

    item_after_edit = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalar_one()
    assert item_after_edit.description == "Produto ISO-25"
    assert item_after_edit.qty == 2
    assert item_after_edit.unit_price == Decimal("100.00")

    history_after_edit_json = await _capture_history_json(db_session, order_id)
    history_after_edit_actions = await _capture_history_actions(db_session, order_id)
    assert history_after_edit_actions == ["created", "edited"]
    assert history_after_edit_json[0] == captured_history_json[0]


async def test_iso22_orc_unique_per_market_contract_exact(
    db_session: AsyncSession,
    client: AsyncClient,
):
    admin_br = await _admin(db_session, "BR")
    admin_eu = await _admin(db_session, "EU")
    pl_br = await _price_list(db_session, "BR", "lojista")
    pl_eu = await _price_list(db_session, "EU", "lojista")
    client_br_id = await _create_client(db_session, "BR", pl_br)
    client_eu_id = await _create_client(db_session, "EU", pl_eu)

    client_br = (
        await db_session.execute(
            select(Client)
            .where(Client.id == client_br_id)
            .execution_options(**_SKIP_SCOPE)
        )
    ).scalar_one()
    client_eu = (
        await db_session.execute(
            select(Client)
            .where(Client.id == client_eu_id)
            .execution_options(**_SKIP_SCOPE)
        )
    ).scalar_one()

    order_br = await make_order(db_session, client_br, admin_br.user_id)
    order_eu = await make_order(db_session, client_eu, admin_eu.user_id)
    await db_session.flush()

    common_orc = f"ORC-ISO22-{uuid.uuid4().hex.upper()}"
    order_br.orc_id = common_orc
    order_eu.orc_id = common_orc
    await db_session.commit()

    response_br = await client.get(
        f"/api/v1/orders/{common_orc}",
        headers=_auth(admin_br.token),
    )
    response_eu = await client.get(
        f"/api/v1/orders/{common_orc}",
        headers=_auth(admin_eu.token),
    )

    assert response_br.status_code == 200
    assert response_eu.status_code == 200
    assert str(response_br.json()["id"]) == str(order_br.id)
    assert str(response_eu.json()["id"]) == str(order_eu.id)


async def test_iso23_cross_market_order_access_returns_404_without_mutation(
    db_session: AsyncSession,
    client: AsyncClient,
):
    admin_br = await _admin(db_session, "BR")
    admin_eu = await _admin(db_session, "EU")
    pl_eu = await _price_list(db_session, "EU", "lojista")
    client_eu_id = await _create_client(db_session, "EU", pl_eu)
    client_eu = (
        await db_session.execute(
            select(Client)
            .where(Client.id == client_eu_id)
            .execution_options(**_SKIP_SCOPE)
        )
    ).scalar_one()
    order_eu = await make_order(db_session, client_eu, admin_eu.user_id)
    await db_session.commit()

    order_id = order_eu.id
    order_uuid = str(order_id)
    orc_id = order_eu.orc_id

    endpoint_uuid = await client.get(
        f"/api/v1/orders/{order_uuid}",
        headers=_auth(admin_br.token),
    )
    endpoint_orc = await client.get(
        f"/api/v1/orders/{orc_id}",
        headers=_auth(admin_br.token),
    )
    endpoint_put = await client.put(
        f"/api/v1/orders/{order_uuid}",
        json={"notes": "tentativa"},
        headers=_auth(admin_br.token),
    )
    endpoint_finalize = await client.post(
        f"/api/v1/orders/{order_uuid}/finalize",
        json={},
        headers=_auth(admin_br.token),
    )
    endpoint_cancel = await client.post(
        f"/api/v1/orders/{order_uuid}/cancel",
        json={},
        headers=_auth(admin_br.token),
    )
    endpoint_delete = await client.delete(
        f"/api/v1/orders/{order_uuid}",
        headers=_auth(admin_br.token),
    )

    assert endpoint_uuid.status_code == 404
    assert endpoint_orc.status_code == 404
    assert endpoint_put.status_code == 404
    assert endpoint_finalize.status_code == 404
    assert endpoint_cancel.status_code == 404
    assert endpoint_delete.status_code == 404

    order_db = (
        await db_session.execute(
            select(Order)
            .where(Order.id == order_id)
            .execution_options(**_SKIP_SCOPE)
        )
    ).scalar_one()

    assert order_db.notes is None
    assert order_db.finalized_at is None
    assert order_db.cancelled_at is None
    assert order_db.is_finalized is False
    assert order_db.is_cancelled is False
    assert order_db.document_version == 1


async def test_representative_order_isolation_lifecycle(db_session: AsyncSession, client: AsyncClient):
    price_list = await _price_list(db_session, 'BR', 'lojista')
    admin = await _admin(db_session, "BR")

    rep_a = await make_representative(db_session, market_code="BR", name="Rep A ISO11")
    rep_b = await make_representative(db_session, market_code="BR", name="Rep B ISO11")
    client_a = await make_client(db_session, price_list, market_code="BR", name="Client A ISO11")
    client_b = await make_client(db_session, price_list, market_code="BR", name="Client B ISO11")
    client_a.rep_id = rep_a.id
    client_b.rep_id = rep_b.id

    product = await _create_product_with_price(db_session, 'BR', price_list, Decimal('80.00'))
    await db_session.commit()

    resp_b = await _post_order(client, admin, client_b.id, [{"product_code": product.product_code, "qty": 1}])
    assert resp_b.status_code == 201, resp_b.text
    order_b_id = uuid.UUID(resp_b.json()["id"])

    user_rep_a = await make_user(
        db_session,
        role=UserRole.representante,
        home_market="BR",
        email=f"repa-{uuid.uuid4()}@ilya-test.invalid",
    )
    await make_user_market(db_session, user_rep_a, market_code="BR", role="representante", rep_id=rep_a.id)
    await db_session.commit()

    token = create_access_token(user_rep_a.id, "representante", user_rep_a.auth_version, "BR")
    headers = {"Authorization": f"Bearer {token}"}

    resp_create_a = await client.post(
        "/api/v1/orders",
        json={"client_id": str(client_a.id), "items": [{"product_code": product.product_code, "qty": 1}]},
        headers=headers,
    )
    assert resp_create_a.status_code == 201, resp_create_a.text

    resp_create_b = await client.post(
        "/api/v1/orders",
        json={"client_id": str(client_b.id), "items": [{"product_code": product.product_code, "qty": 1}]},
        headers=headers,
    )
    assert resp_create_b.status_code == 403, resp_create_b.text

    resp_list = await client.get("/api/v1/orders?limit=100", headers=headers)
    assert resp_list.status_code == 200, resp_list.text
    ids = {o["id"] for o in resp_list.json()}
    assert str(order_b_id) not in ids

    resp_get_b = await client.get(f"/api/v1/orders/{order_b_id}", headers=headers)
    assert resp_get_b.status_code == 404, resp_get_b.text

    resp_put_b = await client.put(
        f"/api/v1/orders/{order_b_id}",
        json={"notes": "tentativa invalida rep a"},
        headers=headers,
    )
    assert resp_put_b.status_code == 404, resp_put_b.text

    order_b_db = (
        await db_session.execute(select(Order).where(Order.id == order_b_id))
    ).scalar_one()
    assert order_b_db.notes is None


async def test_order_rbac_products_role_flow(db_session: AsyncSession, client: AsyncClient):
    price_list = await _price_list(db_session, 'BR', 'lojista')
    admin = await _admin(db_session, "BR")

    product = await _create_product_with_price(db_session, 'BR', price_list, Decimal('50.00'))

    br_client = await make_client(db_session, price_list, market_code="BR", name="Client RBAC BR")
    await db_session.commit()

    resp_admin_order = await _post_order(client, admin, br_client.id, [{"product_code": product.product_code, "qty": 2}])
    assert resp_admin_order.status_code == 201, resp_admin_order.text
    order_id = uuid.UUID(resp_admin_order.json()["id"])

    user_produtos = await make_user(
        db_session,
        role=UserRole.produtos,
        home_market="BR",
        email=f"produtos-{uuid.uuid4()}@ilya-test.invalid",
    )
    await make_user_market(db_session, user_produtos, market_code="BR", role="produtos")
    await db_session.commit()

    produtos_token = create_access_token(user_produtos.id, "produtos", user_produtos.auth_version, "BR")
    produtos_headers = {"Authorization": f"Bearer {produtos_token}"}

    resp_post = await client.post(
        "/api/v1/orders",
        json={"client_id": str(br_client.id), "items": [{"product_code": product.product_code, "qty": 1}]},
        headers=produtos_headers,
    )
    assert resp_post.status_code == 403, resp_post.text

    resp_get = await client.get(f"/api/v1/orders/{order_id}", headers=produtos_headers)
    assert resp_get.status_code == 200, resp_get.text

    resp_put = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"notes": "editado por produtos"},
        headers=produtos_headers,
    )
    assert resp_put.status_code == 200, resp_put.text

    resp_finalize = await client.post(
        f"/api/v1/orders/{order_id}/finalize",
        json={},
        headers=produtos_headers,
    )
    assert resp_finalize.status_code == 200, resp_finalize.text

    order_db = (
        await db_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    assert order_db.is_finalized is True
    assert order_db.notes == "editado por produtos"


async def test_cancel_order_complete_flow(client, db_session):
    admin = await _admin(db_session, 'BR')
    price_list = await _price_list(db_session, 'BR', 'lojista')

    product = await _create_product_with_price(
        db_session, 'BR', price_list, Decimal('100.00')
    )

    client_id = await _create_client(db_session, 'BR', price_list)

    order_data = [{'product_code': product.product_code, 'qty': 1}]
    order_response = await _post_order(client, admin, client_id, order_data)
    assert order_response.status_code == 201, order_response.text
    order_id = uuid.UUID(order_response.json()['id'])

    cancel_response = await _cancel_order(client, admin, order_id)
    assert cancel_response.status_code == 200, cancel_response.text

    result = await db_session.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one()

    assert order.is_cancelled is True
    assert order.cancelled_at is not None
    assert order.is_finalized is False

    history_actions = await _capture_history_actions(db_session, order_id)
    assert history_actions == ['created', 'cancelled']

    put_items_response = await _put_order(client, admin, order_id, order_data)
    assert put_items_response.status_code == 409, put_items_response.text

    finalize_response = await _finalize_order(client, admin, order_id)
    assert finalize_response.status_code == 409, finalize_response.text

    second_cancel_response = await _cancel_order(client, admin, order_id)
    assert second_cancel_response.status_code == 409, second_cancel_response.text

    result = await db_session.execute(
        select(Order).where(Order.id == order_id)
    )
    order_after = result.scalar_one()
    assert order_after.is_cancelled is True
    assert order_after.is_finalized is False

    history_after = await _capture_history_actions(db_session, order_id)
    assert history_after == ['created', 'cancelled']


async def test_create_signed_revision_conflict_and_success(client, db_session):
    admin = await _admin(db_session, 'BR')
    price_list = await _price_list(db_session, 'BR', 'lojista')

    product = await _create_product_with_price(
        db_session, 'BR', price_list, Decimal('100.00')
    )

    client_id = await _create_client(db_session, 'BR', price_list)

    order_data = [{
        'product_code': product.product_code,
        'qty': 2,
        'discount': '0'
    }]

    order_response = await _post_order(client, admin, client_id, order_data)
    assert order_response.status_code == 201, order_response.text
    source_order_id = uuid.UUID(order_response.json()['id'])

    result = await db_session.execute(
        select(OrderItem).where(OrderItem.order_id == source_order_id)
    )
    source_items = result.scalars().all()
    assert len(source_items) == 1

    original_snapshot = await _capture_history_json(db_session, source_order_id)

    result = await db_session.execute(
        select(Order).where(Order.id == source_order_id)
    )
    source_order = result.scalar_one()
    source_order.rep_signature = 'data:image/png;base64,AA=='
    await db_session.commit()

    put_response = await _put_order(client, admin, source_order_id, order_data)
    assert put_response.status_code == 409, put_response.text
    assert 'assinado' in put_response.text.lower() or 'signed' in put_response.text.lower()

    revision_response = await client.post(
        f'/api/v1/orders/{source_order_id}/revision',
        headers={'Authorization': f'Bearer {admin.token}'}
    )
    assert revision_response.status_code == 201, revision_response.text

    successor_order_id = uuid.UUID(revision_response.json()['id'])

    result = await db_session.execute(
        select(Order).where(Order.supersedes_order_id == source_order_id)
    )
    revision_orders = result.scalars().all()
    assert len(revision_orders) == 1

    revision_order = revision_orders[0]
    assert revision_order.id == successor_order_id
    assert revision_order.supersedes_order_id == source_order_id
    assert revision_order.revision_number == 2
    assert revision_order.rep_signature is None or revision_order.rep_signature == ''

    result = await db_session.execute(
        select(Order).where(Order.id == source_order_id)
    )
    source_after = result.scalar_one()
    assert source_after.rep_signature == 'data:image/png;base64,AA=='

    source_snapshot_after = await _capture_history_json(db_session, source_order_id)
    assert source_snapshot_after == original_snapshot

    second_revision_response = await client.post(
        f'/api/v1/orders/{source_order_id}/revision',
        headers={'Authorization': f'Bearer {admin.token}'}
    )
    assert second_revision_response.status_code == 409, second_revision_response.text

    result = await db_session.execute(
        select(Order).where(Order.supersedes_order_id == source_order_id)
    )
    final_revision_orders = result.scalars().all()
    assert len(final_revision_orders) == 1
