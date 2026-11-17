"""IVA único do mercado EU: uma taxa configurável, aplicada só no total.

Contrato (PostgreSQL real, HTTP):

* o IVA é `round_half_up(subtotal × taxa / 100, 2)` sobre o subtotal já com
  descontos, calculado uma vez para o documento; as linhas EU não levam IVA;
* isenção continua valendo (IVA 0, com o motivo);
* o documento grava a taxa usada (`vat_rate`): mudar a taxa nunca altera um
  pedido finalizado, nem um orçamento aberto até ele ser recalculado/editado;
* o BR não muda (IPI por grupo, sem `vat_rate`);
* só admin do EU (ou platform_admin) altera a taxa; o servidor valida 0–100
  com duas casas; toda mudança entra na trilha (quem, quando, de → para).

Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.market import Market, MarketVatRateEvent, ProductPrice
from app.models.order import Order
from app.models.user import UserRole
from tests.factories import make_platform_permission, make_user, make_user_market
from tests.factories.orders import make_order, make_order_item
from tests.integration.test_order_vat_exempt import _deliver
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _SKIP_SCOPE,
    _auth,
    _choice,
    _item,
    _scenario,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

RATE_URL = "/api/v1/markets/EU/vat-rate"


def _full_item(s: Scenario, **extra) -> dict:
    return _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe), **extra)


async def _order(client: AsyncClient, s: Scenario, **fields):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [_full_item(s, qty=fields.pop("qty", 1))], **fields},
        headers=_auth(s.token),
    )


async def _set_rate(client: AsyncClient, s: Scenario, rate: str):
    return await client.put(RATE_URL, json={"vat_rate": rate}, headers=_auth(s.token))


# ── Cálculo ────────────────────────────────────────────────────────────────────

async def test_eu_total_is_subtotal_times_one_plus_rate_and_lines_carry_no_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")  # taxa inicial da migração: 23,00

    response = await _order(client, s, qty=2)

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["vat_rate"]) == Decimal("23.00")
    assert Decimal(body["total_value"]) == Decimal("200.00")
    assert Decimal(body["total_ipi"]) == Decimal("46.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("246.00")
    [line] = body["items"]
    assert Decimal(line["ipi_rate"]) == 0 and Decimal(line["ipi_value"]) == 0


async def test_new_rate_applies_to_new_quotes(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session, "EU")
    assert (await _set_rate(client, s, "6.00")).status_code == 200

    body = (await _order(client, s, qty=2)).json()

    assert Decimal(body["vat_rate"]) == Decimal("6.00")
    assert Decimal(body["total_ipi"]) == Decimal("12.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("212.00")


async def test_vat_is_rounded_once_on_the_total_base(client: AsyncClient, db_session: AsyncSession) -> None:
    """3 × 33,33 = 99,99 → IVA 23% = 22,9977 → 23,00 (um só arredondamento)."""
    s = await _scenario(db_session, "EU")
    await db_session.execute(
        update(ProductPrice).where(ProductPrice.product_id == s.product_id).values(amount=Decimal("33.33"))
    )

    body = (await _order(client, s, qty=3)).json()

    assert Decimal(body["total_value"]) == Decimal("99.99")
    assert Decimal(body["total_ipi"]) == Decimal("23.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("122.99")


async def test_exempt_quote_has_zero_vat_but_keeps_the_rate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")

    body = (await _order(client, s, vat_exempt=True, vat_exemption_code="M16")).json()

    assert body["vat_exempt"] is True
    assert Decimal(body["total_ipi"]) == Decimal("0.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("100.00")
    assert Decimal(body["vat_rate"]) == Decimal("23.00")


async def test_zero_rate_is_a_valid_rate(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session, "EU")
    assert (await _set_rate(client, s, "0")).status_code == 200

    body = (await _order(client, s)).json()

    assert Decimal(body["total_ipi"]) == Decimal("0.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("100.00")


async def test_missing_rate_blocks_quotes_instead_of_billing_without_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    await db_session.execute(update(Market).where(Market.code == "EU").values(vat_rate=None))

    response = await _order(client, s)

    assert response.status_code == 422, response.text
    assert "IVA" in response.json()["detail"]


# ── Documentos fechados são snapshots ──────────────────────────────────────────

async def test_changing_the_rate_never_changes_a_finalized_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = (await _order(client, s, qty=2)).json()
    finalized = await client.post(f"/api/v1/orders/{created['id']}/finalize", json={}, headers=_auth(s.token))
    assert finalized.status_code == 200, finalized.text

    assert (await _set_rate(client, s, "5.00")).status_code == 200

    reloaded = (await client.get(f"/api/v1/orders/{created['id']}", headers=_auth(s.token))).json()
    assert Decimal(reloaded["vat_rate"]) == Decimal("23.00")
    assert Decimal(reloaded["total_ipi"]) == Decimal("46.00")
    assert Decimal(reloaded["total_with_ipi"]) == Decimal("246.00")
    # Só uma revisão (novo documento) passa a usar a taxa nova.
    revision = await client.post(f"/api/v1/orders/{created['id']}/revision", headers=_auth(s.token))
    assert revision.status_code == 201, revision.text
    assert Decimal(revision.json()["vat_rate"]) == Decimal("5.00")
    assert Decimal(revision.json()["total_ipi"]) == Decimal("10.00")


async def test_open_quote_keeps_its_rate_until_edited_then_uses_the_current_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = (await _order(client, s)).json()
    assert (await _set_rate(client, s, "10.00")).status_code == 200

    untouched = (await client.get(f"/api/v1/orders/{created['id']}", headers=_auth(s.token))).json()
    assert Decimal(untouched["total_ipi"]) == Decimal("23.00")

    edited = await client.put(
        f"/api/v1/orders/{created['id']}", json={"items": [_full_item(s, qty=2)]}, headers=_auth(s.token),
    )
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["vat_rate"]) == Decimal("10.00")
    assert Decimal(edited.json()["total_ipi"]) == Decimal("20.00")
    assert Decimal(edited.json()["total_with_ipi"]) == Decimal("220.00")


async def _client_row(db: AsyncSession, s: Scenario):
    from app.models.client import Client

    return (await db.execute(
        select(Client).where(Client.id == s.client_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()


async def test_legacy_per_line_document_is_left_as_it_was(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pedido anterior à taxa única (IVA por linha, `vat_rate` NULL) continua igual."""
    s = await _scenario(db_session, "EU")
    order = await make_order(db_session, await _client_row(db_session, s), s.user_id, market_code="EU")
    item = await make_order_item(db_session, order, unit_price=100.0)
    item.ipi_rate, item.ipi_value = Decimal("23.00"), Decimal("23.00")
    order.total_value, order.total_ipi, order.total_with_ipi = Decimal("100.00"), Decimal("23.00"), Decimal("123.00")
    order.is_finalized = True
    order.finalized_at = order.created_at
    await db_session.commit()
    assert (await _set_rate(client, s, "9.00")).status_code == 200

    body = (await client.get(f"/api/v1/orders/{order.id}", headers=_auth(s.token))).json()

    assert body["vat_rate"] is None
    assert Decimal(body["total_ipi"]) == Decimal("23.00")
    assert Decimal(body["items"][0]["ipi_rate"]) == Decimal("23.00")


# ── BR não muda ────────────────────────────────────────────────────────────────

async def test_brazil_keeps_ipi_per_group_and_has_no_single_vat_rate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")  # grupo com IPI 10%

    body = (await _order(client, s)).json()

    assert body["vat_rate"] is None
    [line] = body["items"]
    assert Decimal(line["ipi_rate"]) == Decimal("10.00") and Decimal(line["ipi_value"]) == Decimal("10.00")
    assert Decimal(body["total_ipi"]) == Decimal("10.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("110.00")
    brazil = await db_session.get(Market, "BR")
    assert brazil.vat_rate is None


# ── Quem altera, validação e trilha ────────────────────────────────────────────

async def test_eu_admin_changes_the_rate_and_the_change_is_audited(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")

    response = await _set_rate(client, s, "21.50")

    assert response.status_code == 200, response.text
    view = response.json()
    assert Decimal(view["vat_rate"]) == Decimal("21.50") and view["can_edit"] is True
    assert view["history"][0]["changed_by"] == "Test User"
    assert Decimal(view["history"][0]["old_rate"]) == Decimal("23.00")
    assert Decimal(view["history"][0]["new_rate"]) == Decimal("21.50")
    events = (await db_session.execute(select(MarketVatRateEvent))).scalars().all()
    assert [(e.actor_user_id, e.old_rate, e.new_rate) for e in events] == [
        (s.user_id, Decimal("23.00"), Decimal("21.50"))
    ]
    # Repetir o valor atual não gera evento.
    assert (await _set_rate(client, s, "21.50")).status_code == 200
    assert len((await db_session.execute(select(MarketVatRateEvent))).scalars().all()) == 1


@pytest.mark.parametrize("bad", ["-1", "100.01", "23.123", "abc"])
async def test_server_rejects_invalid_rates(client: AsyncClient, db_session: AsyncSession, bad: str) -> None:
    s = await _scenario(db_session, "EU")

    response = await _set_rate(client, s, bad)

    assert response.status_code == 422, response.text
    assert Decimal((await db_session.get(Market, "EU")).vat_rate) == Decimal("23.00")


async def test_non_admin_can_read_but_not_change_the_rate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _scenario(db_session, "EU")
    seller = await make_user(db_session, role=UserRole.vendedor, home_market="EU")
    await make_user_market(db_session, seller, market_code="EU", role="vendedor")
    token = create_access_token(seller.id, "vendedor", seller.auth_version, "EU")

    read = await client.get(RATE_URL, headers=_auth(token))
    assert read.status_code == 200 and Decimal(read.json()["vat_rate"]) == Decimal("23.00")
    assert read.json()["can_edit"] is False and read.json()["history"] == []

    write = await client.put(RATE_URL, json={"vat_rate": "1.00"}, headers=_auth(token))
    assert write.status_code == 403, write.text
    assert Decimal((await db_session.get(Market, "EU")).vat_rate) == Decimal("23.00")


async def test_brazil_session_cannot_use_the_eu_rate_endpoints(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    br = await _scenario(db_session, "BR")

    assert (await client.get(RATE_URL, headers=_auth(br.token))).status_code in (403, 404)
    assert (await client.put(RATE_URL, json={"vat_rate": "1.00"}, headers=_auth(br.token))).status_code in (403, 404)
    assert Decimal((await db_session.get(Market, "EU")).vat_rate) == Decimal("23.00")


async def test_platform_admin_changes_the_rate_and_others_cannot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email=f"vat-platform-{uuid.uuid4().hex[:6]}@ilya-test.invalid")
    await make_platform_permission(db_session, admin, capability="platform_admin")
    outbox_only = await make_user(db_session, email=f"vat-outbox-{uuid.uuid4().hex[:6]}@ilya-test.invalid")
    await make_platform_permission(db_session, outbox_only, capability="read_outbox")
    admin_token = create_access_token(admin.id, None, admin.auth_version, None, scope="platform")
    other_token = create_access_token(outbox_only.id, None, outbox_only.auth_version, None, scope="platform")

    denied = await client.put(f"{RATE_URL}/platform", json={"vat_rate": "7"}, headers=_auth(other_token))
    assert denied.status_code == 403, denied.text
    allowed = await client.put(f"{RATE_URL}/platform", json={"vat_rate": "7"}, headers=_auth(admin_token))
    assert allowed.status_code == 200, allowed.text
    assert Decimal(allowed.json()["vat_rate"]) == Decimal("7.00")
    event = (await db_session.execute(select(MarketVatRateEvent))).scalar_one()
    assert event.actor_user_id == admin.id


# ── Moloni ─────────────────────────────────────────────────────────────────────

async def test_moloni_sends_the_single_rate_on_every_line(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    s = await _scenario(db_session, "EU")
    created = await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [_full_item(s), _full_item(s, qty=3)]},
        headers=_auth(s.token),
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))

    fake = await _deliver(db_session, monkeypatch, s, order_id)

    [estimate] = [data for endpoint, data in fake.calls if endpoint == "estimates/insert"]
    assert [line["taxes"] for line in estimate["products"]] == [
        [{"tax_id": 11, "value": 23.0, "order": 1, "cumulative": 0}],
        [{"tax_id": 11, "value": 23.0, "order": 1, "cumulative": 0}],
    ]


async def test_moloni_legacy_per_line_document_keeps_its_line_tax(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    s = await _scenario(db_session, "EU")
    created = (await _order(client, s)).json()
    order_id = created["id"]
    await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))
    # Documento anterior à taxa única: IVA na linha e sem taxa gravada no pedido.
    order = (await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id)).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    order.vat_rate = None
    order.items[0].ipi_rate, order.items[0].ipi_value = Decimal("23.00"), Decimal("23.00")
    await db_session.flush()

    fake = await _deliver(db_session, monkeypatch, s, order_id)

    [estimate] = [data for endpoint, data in fake.calls if endpoint == "estimates/insert"]
    [line] = estimate["products"]
    assert line["taxes"] == [{"tax_id": 11, "value": 23.0, "order": 1, "cumulative": 0}]


async def test_rate_snapshot_survives_in_the_database(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session, "EU")
    created = (await _order(client, s)).json()

    row = (await db_session.execute(
        select(Order.vat_rate, Order.total_ipi).where(Order.id == uuid.UUID(created["id"]))
        .execution_options(**_SKIP_SCOPE)
    )).one()

    assert (Decimal(row.vat_rate), Decimal(row.total_ipi)) == (Decimal("23.00"), Decimal("23.00"))
