"""Item "Especial" do orçamento EU: preço ±%, código PAI-En, comentário obrigatório.

Contrato: o especial é uma linha nova com o código do pai preservado em
`product_code` e o código próprio em `special_code`; o servidor calcula o preço
(base × (100 + %) / 100, arredondado uma vez) sem o teto de desconto; finalizar
exige comentário; cópia mantém código, % e comentário; BR não muda; conta de
cliente não cria especial. Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import UserRole
from tests.factories import make_user, make_user_market
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _auth,
    _choice,
    _item,
    _scenario,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _normal(s: Scenario, **extra) -> dict:
    return _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe), **extra)


def _special(s: Scenario, percent: str | int, **extra) -> dict:
    return _normal(s, is_special=True, special_percent=percent, **extra)


async def _post(client: AsyncClient, s: Scenario, items: list[dict], token: str | None = None):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": items},
        headers=_auth(token or s.token),
    )


async def test_special_price_up_and_down_ignores_discount_ceiling_and_keeps_parent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    response = await _post(client, s, [
        _normal(s),
        _special(s, "15", comment="tampo maior"),
        _special(s, "-20", comment="sem tampo"),
        _special(s, "250", comment="muito acima do teto de desconto"),
    ])
    assert response.status_code == 201, response.text
    body = response.json()
    normal, up, down, big = body["items"]
    assert normal["is_special"] is False and normal["special_code"] is None
    assert [i["special_code"] for i in (up, down, big)] == [
        f"{s.product_code}-E1", f"{s.product_code}-E2", f"{s.product_code}-E3",
    ]
    assert all(i["product_code"] == s.product_code for i in body["items"])
    assert all(i["special_code"] != i["product_code"] for i in (up, down, big))
    assert [Decimal(i["unit_price"]) for i in (up, down, big)] == [
        Decimal("115.00"), Decimal("80.00"), Decimal("350.00"),
    ]
    assert all(Decimal(i["discount"]) == 0 for i in (up, down, big))
    assert all(i["description"].startswith("ESPECIAL - ") for i in (up, down, big))
    assert not normal["description"].startswith("ESPECIAL")
    assert Decimal(body["total_value"]) == Decimal("645.00")
    # IVA 23% calculado no servidor sobre o preço resultante.
    assert Decimal(up["ipi_value"]) == Decimal("26.45")
    snapshot = body["history"][0]["items_snapshot"]
    assert [row["special_code"] for row in snapshot[1:]] == [i["special_code"] for i in (up, down, big)]
    assert snapshot[1]["is_special"] is True and Decimal(snapshot[1]["special_percent"]) == Decimal("15")
    assert snapshot[1]["product_code"] == s.product_code and snapshot[1]["comment"] == "tampo maior"


async def test_normal_line_still_capped_by_discount_ceiling(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    response = await _post(client, s, [_normal(s, discount=50)])
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("percent", ["-100", "-150", "1000.01", "5000"])
async def test_special_percent_limits_rejected(
    client: AsyncClient, db_session: AsyncSession, percent: str
) -> None:
    s = await _scenario(db_session, "EU")
    response = await _post(client, s, [_special(s, percent, comment="x")])
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("percent", ["-99.99", "0", "1000"])
async def test_special_percent_sane_edges_accepted(
    client: AsyncClient, db_session: AsyncSession, percent: str
) -> None:
    s = await _scenario(db_session, "EU")
    response = await _post(client, s, [_special(s, percent)])
    assert response.status_code == 201, response.text


async def test_special_with_discount_or_orphan_special_fields_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    assert (await _post(client, s, [_special(s, "10", discount=5)])).status_code == 422
    assert (await _post(client, s, [_normal(s, special_percent="10")])).status_code == 422
    assert (await _post(client, s, [_normal(s, is_special=True)])).status_code == 422


async def test_special_code_must_belong_to_parent_and_be_unique(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    foreign = await _post(client, s, [_special(s, "5", special_code="OUTRO-E1")])
    assert foreign.status_code == 422, foreign.text
    duplicate = await _post(client, s, [
        _special(s, "5", special_code=f"{s.product_code}-E1"),
        _special(s, "6", special_code=f"{s.product_code}-E1"),
    ])
    assert duplicate.status_code == 422, duplicate.text
    equal_to_parent = await _post(client, s, [_special(s, "5", special_code=s.product_code)])
    assert equal_to_parent.status_code == 422, equal_to_parent.text


async def test_save_without_comment_allowed_but_finalize_blocked_until_commented(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, [_special(s, "10")])
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    code = created.json()["items"][0]["special_code"]

    blocked = await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))
    assert blocked.status_code == 409, blocked.text
    assert code in blocked.json()["detail"] and "comment" in blocked.json()["detail"]
    assert (await client.get(f"/api/v1/orders/{order_id}", headers=_auth(s.token))).json()["is_finalized"] is False

    blank = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"items": [_special(s, "10", special_code=code, comment="   ")]},
        headers=_auth(s.token),
    )
    assert blank.status_code == 200, blank.text
    assert (await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))).status_code == 409

    fixed = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"items": [_special(s, "10", special_code=code, comment="acabamento sob medida")]},
        headers=_auth(s.token),
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["items"][0]["special_code"] == code
    done = await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))
    assert done.status_code == 200, done.text
    assert done.json()["is_finalized"] is True


async def test_edit_keeps_codes_stable_and_assigns_next_free(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, [_special(s, "10", comment="a"), _special(s, "20", comment="b")])
    first, second = (i["special_code"] for i in created.json()["items"])
    edited = await client.put(
        f"/api/v1/orders/{created.json()['id']}",
        json={"items": [
            _special(s, "30", special_code=second, comment="b"),
            _special(s, "5", comment="c"),
        ]},
        headers=_auth(s.token),
    )
    assert edited.status_code == 200, edited.text
    items = {i["special_code"]: i for i in edited.json()["items"]}
    assert set(items) == {first, second}
    assert Decimal(items[second]["unit_price"]) == Decimal("130.00")


async def test_copy_keeps_special_as_is_and_recalculates_price(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, [_normal(s), _special(s, "-20", comment="medida do cliente")])
    body = created.json()
    special = next(i for i in body["items"] if i["is_special"])

    copied = await client.post(
        f"/api/v1/orders/{body['id']}/copy", json={"item_ids": [special["id"]]}, headers=_auth(s.token),
    )
    assert copied.status_code == 201, copied.text
    assert copied.json()["skipped"] == []
    [item] = copied.json()["order"]["items"]
    assert item["is_special"] is True
    assert item["special_code"] == special["special_code"]
    assert Decimal(item["special_percent"]) == Decimal("-20")
    assert item["comment"] == "medida do cliente"
    assert item["description"].startswith("ESPECIAL - ")
    assert Decimal(item["unit_price"]) == Decimal("80.00")
    assert Decimal(copied.json()["order"]["total_value"]) == Decimal("80.00")


async def test_revision_preserves_special(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, [_special(s, "12.5", comment="ok")])
    order_id = created.json()["id"]
    assert (await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))).status_code == 200
    revision = await client.post(f"/api/v1/orders/{order_id}/revision", headers=_auth(s.token))
    assert revision.status_code == 201, revision.text
    [item] = revision.json()["items"]
    assert item["is_special"] is True and item["special_code"] == created.json()["items"][0]["special_code"]
    assert Decimal(item["special_percent"]) == Decimal("12.5")
    assert Decimal(item["unit_price"]) == Decimal("112.50")


async def test_list_exposes_special_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, [_special(s, "10", comment="x")])
    listing = await client.get("/api/v1/orders", headers=_auth(s.token))
    assert listing.status_code == 200, listing.text
    row = next(o for o in listing.json() if o["id"] == created.json()["id"])
    assert row["items"][0]["special_code"] == created.json()["items"][0]["special_code"]


async def test_brazil_rejects_special_and_stays_unchanged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")
    rejected = await _post(client, s, [_special(s, "10", comment="x")])
    assert rejected.status_code == 422, rejected.text
    plain = await _post(client, s, [_normal(s, discount=0)])
    assert plain.status_code == 201, plain.text
    [item] = plain.json()["items"]
    assert item["is_special"] is False and item["special_code"] is None and item["special_percent"] is None
    assert Decimal(item["unit_price"]) == Decimal("100.00")


async def test_client_account_cannot_create_special(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    portal = await make_user(
        db_session, email=f"esp-cli-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole.cliente, home_market="EU",
    )
    portal.linked_id = s.client_id
    await make_user_market(
        db_session, portal, market_code="EU", role="cliente", linked_client_id=s.client_id,
    )
    await db_session.commit()
    token = create_access_token(portal.id, "cliente", portal.auth_version, "EU")

    denied = await _post(client, s, [_special(s, "-90", comment="x")], token)
    assert denied.status_code == 403, denied.text
    allowed = await _post(client, s, [_normal(s)], token)
    assert allowed.status_code == 201, allowed.text
