"""Exclusão de pedido pela API (DELETE /orders/{id}) contra Postgres real.

Contrato: orçamento e pedido sem evidência apagam; pedido com revisão, job do
Moloni ou envio de e-mail é bloqueado com 409 e uma mensagem que diz o motivo.
Nada é apagado nem enfileirado quando bloqueia.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.integration_outbox import IntegrationOutbox
from app.models.moloni import MoloniExportJob
from app.models.optional_application import OrderItemOptionalChoice
from app.models.order import Order, OrderItem
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.order_history import OrderHistory
from app.models.user import UserRole
from tests.factories import make_user, make_user_market
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _auth,
    _choice,
    _item,
    _post_order,
    _scenario,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _new_order(client: AsyncClient, db: AsyncSession, market: str) -> tuple[Scenario, uuid.UUID]:
    s = await _scenario(db, market)
    created = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black), qty=2),
    ])
    assert created.status_code == 201, created.text
    return s, uuid.UUID(created.json()["id"])


def _delete(client: AsyncClient, token: str, order_id):
    return client.delete(f"/api/v1/orders/{order_id}", headers=_auth(token))


def _finalize(client: AsyncClient, s: Scenario, order_id):
    return client.post(f"/api/v1/orders/{order_id}/finalize", json={}, headers=_auth(s.token))


async def _count(db: AsyncSession, model, **where) -> int:
    stmt = select(func.count()).select_from(model)
    for col, value in where.items():
        stmt = stmt.where(getattr(model, col) == value)
    return (await db.execute(stmt.execution_options(skip_market_scope=True))).scalar_one()


async def _outbox_deleted(db: AsyncSession) -> int:
    return await _count(db, IntegrationOutbox, event_type="order.deleted")


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_delete_simple_quote_removes_items_choices_and_history(client, db_session, market):
    s, order_id = await _new_order(client, db_session, market)
    assert await _count(db_session, OrderItemOptionalChoice) > 0

    response = await _delete(client, s.token, order_id)

    assert response.status_code == 204, response.text
    assert await _count(db_session, Order, id=order_id) == 0
    assert await _count(db_session, OrderItem, order_id=order_id) == 0
    assert await _count(db_session, OrderHistory, order_id=order_id) == 0
    assert await _count(db_session, OrderItemOptionalChoice) == 0
    assert await _outbox_deleted(db_session) == 1


async def test_delete_finalized_br_without_email_records(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "off")
    s, order_id = await _new_order(client, db_session, "BR")
    assert (await _finalize(client, s, order_id)).status_code == 200

    assert (await _delete(client, s.token, order_id)).status_code == 204
    assert await _count(db_session, Order, id=order_id) == 0


async def test_finalized_br_with_email_is_blocked_with_clear_message(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "test")
    s, order_id = await _new_order(client, db_session, "BR")
    assert (await _finalize(client, s, order_id)).status_code == 200
    assert await _count(db_session, OrderEmailDocument, order_id=order_id) == 1

    response = await _delete(client, s.token, order_id)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail == "Pedido já teve envio de e-mail registrado e não pode ser excluído."
    assert await _count(db_session, Order, id=order_id) == 1
    assert await _count(db_session, OrderEmailDelivery, order_id=order_id) == 1
    assert await _outbox_deleted(db_session) == 0


@pytest.mark.parametrize("email_mode", ["off", "test"])
async def test_finalized_eu_with_moloni_job_is_blocked(client, db_session, monkeypatch, email_mode):
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", email_mode)
    s, order_id = await _new_order(client, db_session, "EU")
    assert (await _finalize(client, s, order_id)).status_code == 200
    assert await _count(db_session, MoloniExportJob, order_id=order_id) == 1

    response = await _delete(client, s.token, order_id)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail == "Pedido já tem documento no Moloni e não pode ser excluído."
    assert await _count(db_session, Order, id=order_id) == 1
    assert await _outbox_deleted(db_session) == 0


async def test_order_with_revision_is_blocked_until_revision_is_deleted(client, db_session):
    s, order_id = await _new_order(client, db_session, "BR")
    assert (await _finalize(client, s, order_id)).status_code == 200
    revision = await client.post(f"/api/v1/orders/{order_id}/revision", headers=_auth(s.token))
    assert revision.status_code == 201, revision.text
    successor_id = uuid.UUID(revision.json()["id"])

    blocked = await _delete(client, s.token, order_id)

    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == "Este pedido tem uma revisão. Exclua a revisão primeiro."
    assert await _count(db_session, Order, id=order_id) == 1
    assert (await _delete(client, s.token, successor_id)).status_code == 204
    assert (await _delete(client, s.token, order_id)).status_code == 204


async def test_delete_requires_admin(client, db_session):
    s, order_id = await _new_order(client, db_session, "BR")
    rep = await make_user(db_session, role=UserRole.vendedor, home_market="BR")
    await make_user_market(db_session, rep, market_code="BR", role="vendedor")
    token = create_access_token(rep.id, "vendedor", rep.auth_version, "BR")

    response = await _delete(client, token, order_id)

    assert response.status_code == 403
    assert await _count(db_session, Order, id=order_id) == 1
