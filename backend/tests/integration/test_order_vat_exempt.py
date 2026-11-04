"""Orçamento EU "Sem IVA": o servidor zera o imposto e exige o motivo (código Moloni).

Contrato: flag `vat_exempt` + `vat_exemption_code` gravados no pedido; total, IVA
e linhas calculados no servidor; admin, operador interno e representante podem
marcar, conta de cliente nunca; edição e revisão preservam o flag; o exportador
Moloni manda a linha a 0% com `exemption_reason`. Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.orders import _resolve_vat_exemption
from app.core.config import settings
from app.core.moloni_crypto import encrypt_token
from app.core.security import create_access_token
from app.models.client import Client
from app.models.moloni import (
    MoloniConnection,
    MoloniCustomerLink,
    MoloniExportJob,
    MoloniProductLink,
    MoloniTaxMapping,
)
from app.models.product import Product
from app.models.user import UserRole
from app.services import moloni_exporter
from tests.factories import make_user, make_user_market
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _SKIP_SCOPE,
    _auth,
    _choice,
    _item,
    _scenario,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _full_item(s: Scenario, **extra) -> dict:
    return _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe), **extra)


async def _post(client: AsyncClient, s: Scenario, token: str | None = None, **fields):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [_full_item(s)], **fields},
        headers=_auth(token or s.token),
    )


# ── Cálculo no servidor ────────────────────────────────────────────────────────

async def test_exempt_order_has_zero_vat_total_reason_and_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")

    taxed = await _post(client, s)
    assert taxed.status_code == 201, taxed.text
    assert Decimal(taxed.json()["total_ipi"]) == Decimal("23.00")
    assert taxed.json()["vat_exempt"] is False and taxed.json()["vat_exemption_label"] is None

    response = await _post(client, s, vat_exempt=True, vat_exemption_code="M16", locale="en-GB")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["vat_exempt"] is True and body["vat_exemption_code"] == "M16"
    assert "intra-Community" in body["vat_exemption_label"]
    assert Decimal(body["total_value"]) == Decimal("100.00")
    assert Decimal(body["total_ipi"]) == Decimal("0.00")
    assert Decimal(body["total_with_ipi"]) == Decimal("100.00")
    [item] = body["items"]
    assert Decimal(item["ipi_rate"]) == 0 and Decimal(item["ipi_value"]) == 0
    assert body["history"][0]["details"] == "IVA isento (M16)"

    reloaded = await client.get(f"/api/v1/orders/{body['id']}", headers=_auth(s.token))
    assert reloaded.json()["vat_exempt"] is True
    assert Decimal(reloaded.json()["total_ipi"]) == 0


async def test_exemption_requires_valid_reason_and_eu_market(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_eu = await _scenario(db_session, "EU")
    s_br = await _scenario(db_session, "BR")

    no_code = await _post(client, s_eu, vat_exempt=True)
    assert no_code.status_code == 422, no_code.text
    bad_code = await _post(client, s_eu, vat_exempt=True, vat_exemption_code="M00")
    assert bad_code.status_code == 422, bad_code.text
    brazil = await _post(client, s_br, vat_exempt=True, vat_exemption_code="M16")
    assert brazil.status_code == 422, brazil.text


async def test_edit_keeps_flag_and_can_toggle_it_with_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, vat_exempt=True, vat_exemption_code="M05")
    order_id = created.json()["id"]

    kept = await client.put(
        f"/api/v1/orders/{order_id}", json={"items": [_full_item(s, qty=2)]}, headers=_auth(s.token),
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["vat_exempt"] is True
    assert Decimal(kept.json()["total_value"]) == Decimal("200.00")
    assert Decimal(kept.json()["total_ipi"]) == 0

    flag_without_items = await client.put(
        f"/api/v1/orders/{order_id}", json={"vat_exempt": False}, headers=_auth(s.token),
    )
    assert flag_without_items.status_code == 422, flag_without_items.text

    removed = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"vat_exempt": False, "items": [_full_item(s, qty=2)]},
        headers=_auth(s.token),
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["vat_exempt"] is False and removed.json()["vat_exemption_code"] is None
    assert Decimal(removed.json()["total_ipi"]) == Decimal("46.00")
    # Os eventos compartilham o created_at da transação do teste: sem depender da ordem.
    assert any("IVA: isenção removida" in (row["details"] or "") for row in removed.json()["history"])


async def test_revision_preserves_exemption(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, vat_exempt=True, vat_exemption_code="M07")
    order_id = created.json()["id"]
    finalized = await client.post(
        f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token),
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["vat_exempt"] is True

    revision = await client.post(f"/api/v1/orders/{order_id}/revision", headers=_auth(s.token))
    assert revision.status_code == 201, revision.text
    assert revision.json()["vat_exempt"] is True
    assert revision.json()["vat_exemption_code"] == "M07"
    assert Decimal(revision.json()["total_ipi"]) == 0


# ── Quem pode marcar ───────────────────────────────────────────────────────────

async def test_client_account_cannot_exempt_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    portal = await make_user(
        db_session, email=f"vat-cli-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole.cliente, home_market="EU",
    )
    portal.linked_id = s.client_id
    await make_user_market(
        db_session, portal, market_code="EU", role="cliente", linked_client_id=s.client_id,
    )
    await db_session.commit()
    token = create_access_token(portal.id, "cliente", portal.auth_version, "EU")

    exempt = await _post(client, s, token, vat_exempt=True, vat_exemption_code="M16")
    assert exempt.status_code == 403, exempt.text
    plain = await _post(client, s, token)
    assert plain.status_code == 201, plain.text
    assert plain.json()["vat_exempt"] is False


@pytest.mark.parametrize(
    ("role", "linked_id", "allowed"),
    [
        (UserRole.admin, None, True),
        (UserRole.representante, None, True),
        (UserRole.vendedor, None, True),              # operador interno
        (UserRole.vendedor, uuid.uuid4(), False),     # legado: conta de cliente
        (UserRole.cliente, uuid.uuid4(), False),
        (UserRole.produtos, None, False),
    ],
)
async def test_vat_exemption_permission_matrix(role, linked_id, allowed) -> None:
    user = SimpleNamespace(role=role, linked_id=linked_id)
    if allowed:
        assert _resolve_vat_exemption(user, "EU", True, "M16", (False, None)) == (True, "M16")
        assert _resolve_vat_exemption(user, "EU", False, None, (True, "M16")) == (False, None)
    else:
        with pytest.raises(HTTPException) as denied:
            _resolve_vat_exemption(user, "EU", True, "M16", (False, None))
        assert denied.value.status_code == 403
    # Ausente nunca exige permissão: só herda o estado atual.
    assert _resolve_vat_exemption(user, "EU", None, None, (True, "M16")) == (True, "M16")


# ── Moloni ─────────────────────────────────────────────────────────────────────

class _FakeMoloniApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, endpoint: str, data: dict):
        self.calls.append((endpoint, data))
        if endpoint == "salesmen/getAll":
            return [{"salesman_id": 1}]
        if endpoint == "taxes/getAll":
            return [
                {"tax_id": 11, "value": 23, "active_by_default": 1},
                {"tax_id": 12, "value": 0, "active_by_default": 1},
            ]
        if endpoint == "estimates/insert":
            return {"document_id": 77}
        raise AssertionError(f"endpoint inesperado: {endpoint}")


async def _deliver(db: AsyncSession, monkeypatch, s: Scenario, order_id: str) -> _FakeMoloniApi:
    fake = _FakeMoloniApi()
    monkeypatch.setattr(settings, "MOLONI_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(moloni_exporter, "MoloniApi", lambda *_a, **_k: fake)
    monkeypatch.setattr(moloni_exporter, "_configured", lambda: True)
    connection = MoloniConnection(
        company_id=900_000 + uuid.uuid4().int % 90_000,
        access_token_ciphertext=encrypt_token("token"),
        refresh_token_ciphertext=encrypt_token("refresh"),
        is_active=True,
    )
    db.add(connection)
    await db.flush()
    product = (await db.execute(
        select(Product).where(Product.id == s.product_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    db.add_all([
        MoloniTaxMapping(connection_id=connection.id, vat_rate=Decimal("23.00"), moloni_tax_id=11),
        MoloniCustomerLink(connection_id=connection.id, client_id=s.client_id, moloni_customer_id=5),
        MoloniProductLink(connection_id=connection.id, product_id=product.id, moloni_product_id=6),
    ])
    # A finalização já enfileirou o job deste pedido.
    job = (await db.execute(
        select(MoloniExportJob).where(MoloniExportJob.order_id == uuid.UUID(order_id))
    )).scalar_one()
    client_row = (await db.execute(
        select(Client).where(Client.id == s.client_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    client_row.tax_id = "999999990"  # o exportador exige NIF
    await db.flush()
    assert await moloni_exporter.deliver_job(db, job) == 77
    return fake


async def test_moloni_sends_exempt_line_with_reason(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s, vat_exempt=True, vat_exemption_code="M16")
    order_id = created.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))

    fake = await _deliver(db_session, monkeypatch, s, order_id)
    [estimate] = [data for endpoint, data in fake.calls if endpoint == "estimates/insert"]
    [line] = estimate["products"]
    assert line["taxes"] == [{"tax_id": 12, "value": 0.0, "order": 1, "cumulative": 0}]
    assert line["exemption_reason"] == "M16"


async def test_moloni_taxed_line_is_unchanged(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post(client, s)
    order_id = created.json()["id"]
    await client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))

    fake = await _deliver(db_session, monkeypatch, s, order_id)
    [estimate] = [data for endpoint, data in fake.calls if endpoint == "estimates/insert"]
    [line] = estimate["products"]
    assert line["taxes"] == [{"tax_id": 11, "value": 23.0, "order": 1, "cumulative": 0}]
    assert "exemption_reason" not in line
