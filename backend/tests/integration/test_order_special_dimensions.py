"""Medidas editáveis na linha Especial (EU): valem só para a linha.

Contrato: `special_width_m` / `special_depth_m` / `special_height_m` (METROS,
2 casas, > 0 e <= 20) substituem as medidas do produto no snapshot da linha
(`order_items.largura/profundidade/altura`); eixo omitido mantém a medida do
produto; o cadastro e a linha normal não mudam; o preço continua base × (100 + %).
Cópia e revisão preservam a medida. Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import make_user, make_user_market
from tests.integration.test_optional_applications_flow import (
    _SKIP_SCOPE,
    Scenario,
    _auth,
    _choice,
    _item,
    _scenario,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH = Decimal("0.75"), Decimal("1.20"), Decimal("0.50")


async def _scenario_with_dimensions(db: AsyncSession) -> Scenario:
    s = await _scenario(db, "EU")
    await db.execute(
        update(Product).where(Product.id == s.product_id)
        .values(altura=PRODUCT_HEIGHT, largura=PRODUCT_WIDTH, profundidade=PRODUCT_DEPTH)
    )
    await db.commit()
    db.expunge_all()
    return s


def _normal(s: Scenario, **extra) -> dict:
    return _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe), **extra)


def _special(s: Scenario, percent: str | int = "10", **extra) -> dict:
    extra.setdefault("comment", "medida sob encomenda")
    return _normal(s, is_special=True, special_percent=percent, **extra)


async def _post(client: AsyncClient, s: Scenario, items: list[dict]):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": items},
        headers=_auth(s.token),
    )


def _dims(item: dict) -> tuple[Decimal, Decimal, Decimal]:
    return Decimal(item["altura"]), Decimal(item["largura"]), Decimal(item["profundidade"])


async def _product_dims(db: AsyncSession, s: Scenario) -> tuple[Decimal, Decimal, Decimal]:
    row = (await db.execute(
        select(Product.altura, Product.largura, Product.profundidade)
        .where(Product.id == s.product_id).execution_options(populate_existing=True, **_SKIP_SCOPE)
    )).one()
    return Decimal(row.altura), Decimal(row.largura), Decimal(row.profundidade)


async def test_special_dimensions_stored_on_line_only_and_price_unchanged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    response = await _post(client, s, [
        _normal(s),
        _special(s, "10", special_width_m="1.45", special_depth_m="0.60", special_height_m="0.80"),
    ])
    assert response.status_code == 201, response.text
    normal, special = response.json()["items"]

    assert _dims(normal) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH)
    assert _dims(special) == (Decimal("0.80"), Decimal("1.45"), Decimal("0.60"))
    # Preço continua base × (100 + %) / 100: medida não reprecifica.
    assert Decimal(special["unit_price"]) == Decimal("110.00")
    assert Decimal(normal["unit_price"]) == Decimal("100.00")
    # Produto pai (cadastro) intacto.
    assert await _product_dims(db_session, s) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH)

    snapshot = response.json()["history"][0]["items_snapshot"]
    assert "largura" not in snapshot[0]
    assert Decimal(snapshot[1]["largura"]) == Decimal("1.45")
    assert Decimal(snapshot[1]["altura"]) == Decimal("0.80")


async def test_omitted_axes_keep_the_product_dimension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    response = await _post(client, s, [_special(s, special_width_m="2")])
    assert response.status_code == 201, response.text
    [special] = response.json()["items"]
    assert _dims(special) == (PRODUCT_HEIGHT, Decimal("2.00"), PRODUCT_DEPTH)

    plain = await _post(client, s, [_special(s)])
    assert _dims(plain.json()["items"][0]) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH)


@pytest.mark.parametrize("field", ["special_width_m", "special_depth_m", "special_height_m"])
@pytest.mark.parametrize("value", ["20.01", "470", "0", "-0.5", "1.234"])
async def test_special_dimension_limits_rejected(
    client: AsyncClient, db_session: AsyncSession, field: str, value: str
) -> None:
    s = await _scenario_with_dimensions(db_session)
    response = await _post(client, s, [_special(s, **{field: value})])
    assert response.status_code == 422, response.text
    assert await _product_dims(db_session, s) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH)


async def test_special_dimension_at_the_limit_is_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    response = await _post(client, s, [_special(s, special_width_m="20", special_height_m="0.01")])
    assert response.status_code == 201, response.text
    assert _dims(response.json()["items"][0])[:2] == (Decimal("0.01"), Decimal("20.00"))


async def test_dimensions_without_special_are_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    response = await _post(client, s, [_normal(s, special_width_m="1.5")])
    assert response.status_code == 422, response.text


async def test_edit_changes_and_removing_the_override_restores_product_dimensions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    created = await _post(client, s, [_special(s, special_width_m="1.45")])
    order_id = created.json()["id"]
    code = created.json()["items"][0]["special_code"]

    changed = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"items": [_special(s, special_code=code, special_depth_m="0.90")]},
        headers=_auth(s.token),
    )
    assert changed.status_code == 200, changed.text
    assert _dims(changed.json()["items"][0]) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, Decimal("0.90"))

    # Desligar o especial (linha normal) volta às medidas do produto.
    normal = await client.put(
        f"/api/v1/orders/{order_id}", json={"items": [_normal(s)]}, headers=_auth(s.token),
    )
    assert normal.status_code == 200, normal.text
    assert _dims(normal.json()["items"][0]) == (PRODUCT_HEIGHT, PRODUCT_WIDTH, PRODUCT_DEPTH)
    assert normal.json()["items"][0]["is_special"] is False


async def test_copy_endpoint_and_copy_from_screen_preserve_the_special_dimensions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    created = await _post(client, s, [
        _special(s, "10", special_width_m="1.45", special_depth_m="0.60", special_height_m="0.80"),
    ])
    source = created.json()
    special = source["items"][0]

    copied = await client.post(
        f"/api/v1/orders/{source['id']}/copy", json={"item_ids": [special["id"]]}, headers=_auth(s.token),
    )
    assert copied.status_code == 201, copied.text
    [item] = copied.json()["order"]["items"]
    assert item["special_code"] == special["special_code"]
    assert _dims(item) == (Decimal("0.80"), Decimal("1.45"), Decimal("0.60"))

    # Fluxo novo: a tela reenvia os itens com `copy_source_order_id`.
    screen_copy = await client.post(
        "/api/v1/orders",
        json={
            "client_id": str(s.client_id),
            "copy_source_order_id": source["id"],
            "items": [_special(
                s, "10", special_code=special["special_code"], source_order_item_id=special["id"],
                special_width_m="1.45", special_depth_m="0.60", special_height_m="0.80",
            )],
        },
        headers=_auth(s.token),
    )
    assert screen_copy.status_code == 201, screen_copy.text
    assert _dims(screen_copy.json()["items"][0]) == (Decimal("0.80"), Decimal("1.45"), Decimal("0.60"))

    # Revisão do pedido finalizado também preserva.
    finalized = await client.post(f"/api/v1/orders/{source['id']}/finalize", json={}, headers=_auth(s.token))
    assert finalized.status_code == 200, finalized.text
    revision = await client.post(f"/api/v1/orders/{source['id']}/revision", headers=_auth(s.token))
    assert revision.status_code == 201, revision.text
    assert _dims(revision.json()["items"][0]) == (Decimal("0.80"), Decimal("1.45"), Decimal("0.60"))


async def test_client_account_cannot_send_special_dimensions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario_with_dimensions(db_session)
    portal = await make_user(
        db_session, email=f"dim-cli-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole.cliente, home_market="EU",
    )
    portal.linked_id = s.client_id
    await make_user_market(db_session, portal, market_code="EU", role="cliente", linked_client_id=s.client_id)
    await db_session.commit()
    token = create_access_token(portal.id, "cliente", portal.auth_version, "EU")
    denied = await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [_special(s, special_width_m="1.5")]},
        headers=_auth(token),
    )
    assert denied.status_code == 403, denied.text
