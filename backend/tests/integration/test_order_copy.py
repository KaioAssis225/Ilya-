"""Copiar pedido: POST /orders/{id}/copy cria orçamento novo com os itens escolhidos.

Contrato: só entram os itens selecionados (produto, quantidade/medidas, opcionais,
comentário); preço, desconto e imposto são recalculados com as regras de hoje;
item que não pode ser copiado é avisado e pulado; o pedido de origem não muda;
RBAC e isolamento de mercado valem como na criação. Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.catalog import Catalog
from app.models.market import ProductPrice
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import (
    make_product,
    make_product_market,
    make_product_price,
    make_user,
    make_user_market,
)
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _SKIP_SCOPE,
    _auth,
    _choice,
    _item,
    _post_order,
    _scenario,
    _seeded_price_list,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _two_line_order(client: AsyncClient, s: Scenario) -> dict:
    created = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black),
              qty=1, comment="linha um"),
        _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe),
              qty=2, comment="linha dois"),
    ])
    assert created.status_code == 201, created.text
    return created.json()


def _copy(client: AsyncClient, token: str, order_id: str, item_ids: list[str]):
    return client.post(
        f"/api/v1/orders/{order_id}/copy", json={"item_ids": item_ids}, headers=_auth(token),
    )


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_copy_creates_new_draft_with_only_selected_items_and_fresh_price(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    s = await _scenario(db_session, market)
    source = await _two_line_order(client, s)
    second = next(i for i in source["items"] if i["qty"] == 2)

    # O preço de hoje é outro: a cópia não pode herdar o do pedido antigo.
    await db_session.execute(
        update(ProductPrice).where(ProductPrice.product_id == s.product_id)
        .values(amount=Decimal("150.00"))
    )
    await db_session.commit()
    db_session.expunge_all()

    response = await _copy(client, s.token, source["id"], [second["id"]])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["skipped"] == []
    copied = body["order"]
    assert copied["id"] != source["id"]
    assert copied["is_finalized"] is False and copied["is_cancelled"] is False
    assert copied["client_id"] == source["client_id"]
    assert copied["price_list_code"] == source["price_list_code"]
    assert copied["supersedes_order_id"] is None
    [item] = copied["items"]
    assert item["qty"] == 2 and item["comment"] == "linha dois"
    assert Decimal(item["unit_price"]) == Decimal("150.00")
    assert {c["application_name"]: c["optional_name"] for c in item["optional_choices"]} == {
        "Pés": "Preto", "Encosto": "Taupe",
    }
    assert Decimal(copied["total_value"]) == Decimal("300.00")

    # Origem intacta (2 itens, preço antigo) e histórico da cópia aponta a origem.
    original = (await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(source["id"]))
        .execution_options(populate_existing=True, **_SKIP_SCOPE)
    )).scalar_one()
    assert len(original.items) == 2
    assert Decimal(original.total_value) == Decimal("300.00")
    assert {Decimal(i.unit_price) for i in original.items} == {Decimal("100.00")}
    history = (await db_session.execute(
        select(OrderHistory.details).where(OrderHistory.order_id == uuid.UUID(copied["id"]))
        .execution_options(**_SKIP_SCOPE)
    )).scalars().all()
    assert history == [f"copiado de {source['code']}"]


async def test_copy_discount_is_capped_by_current_ceiling(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EU/lojista não tem desconto: o desconto antigo não vale na cópia."""
    s = await _scenario(db_session, "EU")
    source = await _two_line_order(client, s)
    await db_session.execute(
        update(OrderItem).where(OrderItem.order_id == uuid.UUID(source["id"]))
        .values(discount=Decimal("10.00"))
    )
    await db_session.commit()
    db_session.expunge_all()

    response = await _copy(client, s.token, source["id"], [source["items"][0]["id"]])
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["order"]["items"][0]["discount"]) == Decimal("0")


async def test_copy_skips_inactive_product_and_reports_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")
    price_list = await _seeded_price_list(db_session, "BR", "lojista")
    base = (await db_session.execute(
        select(Product).where(Product.id == s.product_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    catalog = (await db_session.execute(
        select(Catalog).where(Catalog.id == base.catalog_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    other = await make_product(
        db_session, market_code="BR", product_code=f"CPY-{uuid.uuid4().hex[:6].upper()}",
        description="Produto simples", catalog=catalog,
    )
    other.type = base.type
    await make_product_market(db_session, other)
    await make_product_price(db_session, other, price_list, amount=Decimal("80.00"))
    await db_session.commit()

    created = await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [
            _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe)),
            {"product_code": other.product_code, "qty": 1},
        ]},
        headers=_auth(s.token),
    )
    assert created.status_code == 201, created.text
    source = created.json()

    await db_session.execute(
        update(Product).where(Product.id == s.product_id).values(is_active=False)
    )
    await db_session.commit()
    db_session.expunge_all()

    response = await _copy(client, s.token, source["id"], [i["id"] for i in source["items"]])
    assert response.status_code == 201, response.text
    body = response.json()
    assert [i["product_code"] for i in body["order"]["items"]] == [other.product_code]
    assert [row["product_code"] for row in body["skipped"]] == [s.product_code]
    assert "inativo" in body["skipped"][0]["reason"]

    only_inactive = await _copy(
        client, s.token, source["id"],
        [i["id"] for i in source["items"] if i["product_code"] == s.product_code],
    )
    assert only_inactive.status_code == 422
    assert s.product_code in only_inactive.json()["detail"]


async def test_copy_rejects_foreign_item_and_empty_selection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")
    source = await _two_line_order(client, s)
    other = await _two_line_order(client, s)

    foreign = await _copy(client, s.token, source["id"], [other["items"][0]["id"]])
    assert foreign.status_code == 422, foreign.text
    empty = await _copy(client, s.token, source["id"], [])
    assert empty.status_code == 422, empty.text


async def test_copy_is_forbidden_without_create_permission_and_isolated_by_market(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_br = await _scenario(db_session, "BR")
    s_eu = await _scenario(db_session, "EU")
    source = await _two_line_order(client, s_br)
    item_ids = [source["items"][0]["id"]]

    catalog_user = await make_user(
        db_session, email=f"copy-cat-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole.produtos, home_market="BR",
    )
    await make_user_market(db_session, catalog_user, market_code="BR", role="produtos")
    await db_session.commit()
    catalog_token = create_access_token(
        catalog_user.id, "produtos", catalog_user.auth_version, "BR",
    )
    forbidden = await _copy(client, catalog_token, source["id"], item_ids)
    assert forbidden.status_code == 403, forbidden.text

    # Sessão do mercado EU não enxerga pedido do BR.
    cross_market = await _copy(client, s_eu.token, source["id"], item_ids)
    assert cross_market.status_code == 404, cross_market.text

    unauthenticated = await client.post(
        f"/api/v1/orders/{source['id']}/copy", json={"item_ids": item_ids},
    )
    assert unauthenticated.status_code in (401, 403)
