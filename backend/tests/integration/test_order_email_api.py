import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.order_documents import put_document
from app.core.security import create_access_token
from app.models.market import PriceList
from app.models.order_email import (
    OrderEmailDelivery,
    OrderEmailDocument,
    OrderEmailWebhookEvent,
)
from app.models.user import UserRole
from app.workers.order_email_sender import process_due
from tests.factories import make_client, make_user, make_user_market
from tests.factories.orders import make_order


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"


async def _price_list(db, market):
    return (
        await db.execute(
            select(PriceList)
            .where(PriceList.market_code == market)
            .order_by(PriceList.code)
            .limit(1)
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()


async def _context(db, *, market="BR", role=UserRole.admin):
    user = await make_user(db, role=role, home_market=market)
    await make_user_market(db, user, market_code=market, role=role.value)
    customer = await make_client(db, await _price_list(db, market), market_code=market)
    customer.email = "client@example.com"
    order = await make_order(db, customer, user.id, market_code=market)
    await db.flush()
    token = create_access_token(user.id, role.value, user.auth_version, market)
    return user, customer, order, {"Authorization": f"Bearer {token}"}


def _local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    for name in (
        "OBJECT_STORAGE_ENDPOINT",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_BUCKET",
        "OBJECT_STORAGE_EU_ENDPOINT",
        "OBJECT_STORAGE_EU_ACCESS_KEY_ID",
        "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_EU_BUCKET",
    ):
        monkeypatch.setattr(settings, name, "")


async def _ready_document(db, order, monkeypatch, tmp_path):
    _local_storage(monkeypatch, tmp_path)
    key, digest, size = await put_document(
        order.market_code, order.id, order.document_version, _PDF
    )
    document = OrderEmailDocument(
        order_id=order.id,
        market_code=order.market_code,
        version=order.document_version,
        locale=order.locale,
        status="ready",
        attempts=1,
        snapshot={
            "schema_version": 1,
            "locale": order.locale,
            "order": {
                "code": order.code,
                "market_code": order.market_code,
                "locale": order.locale,
            },
        },
        storage_key=key,
        sha256=digest,
        size_bytes=size,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(document)
    await db.flush()
    return document


async def _delivery(db, order, document, **values):
    delivery_id = uuid.uuid4()
    delivery = OrderEmailDelivery(
        id=delivery_id,
        order_id=order.id,
        market_code=order.market_code,
        document_id=document.id,
        recipient_roles=values.pop("recipient_roles", ["client"]),
        recipient_email=values.pop("recipient_email", "client@example.com"),
        recipient_name="Test Client",
        origin=values.pop("origin", "finalization"),
        status=values.pop("status", "accepted"),
        attempts=values.pop("attempts", 1),
        idempotency_key=f"order-email/{delivery_id}",
        **values,
    )
    db.add(delivery)
    await db.flush()
    return delivery


def _webhook_headers(secret_key: bytes, event_id: str, body: bytes):
    timestamp = str(int(time.time()))
    signed = f"{event_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(
        hmac.new(secret_key, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": event_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
        "content-type": "application/json",
    }


async def test_history_is_empty_for_non_retroactive_order(client, db_session):
    _, _, order, headers = await _context(db_session)

    response = await client.get(f"/api/v1/orders/{order.id}/emails", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"document": None, "deliveries": []}


async def test_download_returns_exact_bytes_and_private_headers(
    client, db_session, monkeypatch, tmp_path
):
    _, _, order, headers = await _context(db_session)
    await _ready_document(db_session, order, monkeypatch, tmp_path)

    response = await client.get(
        f"/api/v1/orders/{order.id}/email-document", headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.content == _PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert order.code in response.headers["content-disposition"]


async def test_other_market_sees_same_404_as_missing_order(
    client, db_session, monkeypatch, tmp_path
):
    _, _, eu_order, _ = await _context(db_session, market="EU")
    await _ready_document(db_session, eu_order, monkeypatch, tmp_path)
    _, _, _, br_headers = await _context(db_session, market="BR")

    history = await client.get(
        f"/api/v1/orders/{eu_order.id}/emails", headers=br_headers
    )
    download = await client.get(
        f"/api/v1/orders/{eu_order.id}/email-document", headers=br_headers
    )

    assert history.status_code == download.status_code == 404
    assert history.json()["detail"] == download.json()["detail"] == "Pedido não encontrado."


async def test_manual_resend_uses_same_document_and_current_corrected_address(
    client, db_session, monkeypatch, tmp_path
):
    _, customer, order, headers = await _context(db_session)
    document = await _ready_document(db_session, order, monkeypatch, tmp_path)
    original = await _delivery(
        db_session,
        order,
        document,
        recipient_email=None,
        status="blocked",
        attempts=0,
        last_error="missing_recipient",
    )
    customer.email = "corrected@example.com"
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    response = await client.post(
        f"/api/v1/orders/{order.id}/emails/resend",
        json={"delivery_id": str(original.id), "use_current_address": True},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    created = await db_session.get(OrderEmailDelivery, uuid.UUID(response.json()["id"]))
    assert created.document_id == original.document_id
    assert created.recipient_email == "corrected@example.com"
    assert created.idempotency_key != original.idempotency_key
    assert created.resend_of_id == original.id
    assert document.sha256 and document.storage_key


async def test_non_operator_cannot_resend(client, db_session, monkeypatch, tmp_path):
    _, _, order, _ = await _context(db_session)
    document = await _ready_document(db_session, order, monkeypatch, tmp_path)
    original = await _delivery(db_session, order, document, status="failed")
    user = await make_user(db_session, role=UserRole.cadastros, home_market="BR")
    await make_user_market(db_session, user, market_code="BR", role="cadastros")
    token = create_access_token(user.id, "cadastros", user.auth_version, "BR")
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    response = await client.post(
        f"/api/v1/orders/{order.id}/emails/resend",
        json={"delivery_id": str(original.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_webhook_rejects_invalid_signature_and_deduplicates_delivery(
    client, db_session, monkeypatch, tmp_path
):
    _, _, order, _ = await _context(db_session)
    document = await _ready_document(db_session, order, monkeypatch, tmp_path)
    delivery = await _delivery(
        db_session,
        order,
        document,
        provider_message_id="provider-1",
        accepted_at=datetime.now(timezone.utc),
    )
    key = b"integration-webhook-key"
    monkeypatch.setattr(
        settings,
        "RESEND_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(key).decode(),
    )
    body = json.dumps(
        {
            "type": "email.delivered",
            "created_at": "2026-10-29T12:00:00Z",
            "data": {"email_id": "provider-1", "to": ["private@example.com"]},
        },
        separators=(",", ":"),
    ).encode()

    invalid = await client.post(
        "/webhooks/resend",
        content=body,
        headers={
            "svix-id": "event-invalid",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,invalid",
        },
    )
    assert invalid.status_code == 401

    headers = _webhook_headers(key, "event-1", body)
    first = await client.post("/webhooks/resend", content=body, headers=headers)
    repeated = await client.post("/webhooks/resend", content=body, headers=headers)
    assert first.status_code == repeated.status_code == 200
    await db_session.refresh(delivery)
    assert delivery.status == "delivered"
    assert (await db_session.execute(select(func.count()).select_from(OrderEmailWebhookEvent))).scalar_one() == 1
    event = (await db_session.execute(select(OrderEmailWebhookEvent))).scalar_one()
    assert event.payload_summary == {
        "type": "email.delivered",
        "message_id": "provider-1",
        "timestamp": "2026-10-29T12:00:00+00:00",
    }


async def test_out_of_order_webhook_does_not_replace_terminal_status(
    client, db_session, monkeypatch, tmp_path
):
    _, _, order, _ = await _context(db_session)
    document = await _ready_document(db_session, order, monkeypatch, tmp_path)
    delivery = await _delivery(
        db_session, order, document, provider_message_id="provider-2"
    )
    key = b"integration-webhook-key"
    monkeypatch.setattr(
        settings,
        "RESEND_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(key).decode(),
    )
    for index, event_type in enumerate(("email.delivered", "email.failed"), 1):
        body = json.dumps(
            {"type": event_type, "data": {"email_id": "provider-2"}},
            separators=(",", ":"),
        ).encode()
        response = await client.post(
            "/webhooks/resend",
            content=body,
            headers=_webhook_headers(key, f"event-order-{index}", body),
        )
        assert response.status_code == 200
    await db_session.refresh(delivery)
    assert delivery.status == "delivered"


async def test_worker_scan_applies_orphan_webhook_when_provider_id_becomes_known(
    client, db_session, monkeypatch, tmp_path
):
    _, _, order, _ = await _context(db_session)
    document = await _ready_document(db_session, order, monkeypatch, tmp_path)
    delivery = await _delivery(
        db_session, order, document, status="accepted", attempts=1
    )
    key = b"integration-webhook-key"
    monkeypatch.setattr(
        settings,
        "RESEND_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(key).decode(),
    )
    body = json.dumps(
        {"type": "email.delivered", "data": {"email_id": "provider-before"}},
        separators=(",", ":"),
    ).encode()

    response = await client.post(
        "/webhooks/resend",
        content=body,
        headers=_webhook_headers(key, "event-before", body),
    )
    assert response.status_code == 200
    event = (await db_session.execute(select(OrderEmailWebhookEvent))).scalar_one()
    assert event.delivery_id is None and event.applied_at is None

    delivery.provider_message_id = "provider-before"
    await db_session.commit()
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "")

    await process_due(db_session)
    await db_session.refresh(delivery)
    await db_session.refresh(event)

    assert delivery.status == "delivered"
    assert event.delivery_id == delivery.id
    assert event.applied_at is not None
