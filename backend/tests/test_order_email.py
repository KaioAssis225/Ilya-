import base64
import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models.order_email import OrderDocument, OrderEmailDelivery
from app.services import order_email as order_email_service
from app.services.order_email import decode_pdf_payload
from app.services.resend_webhook import apply_event, verify_signature
from app.workers import order_email_sender


PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def test_decode_pdf_payload_accepts_complete_pdf():
    assert decode_pdf_payload(base64.b64encode(PDF).decode()) == PDF


@pytest.mark.parametrize("payload", [None, "", "not-base64", base64.b64encode(b"not pdf").decode()])
def test_decode_pdf_payload_rejects_missing_or_invalid_payload(payload):
    with pytest.raises(HTTPException) as exc:
        decode_pdf_payload(payload)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_delivery_rows_deduplicates_equal_recipient_addresses(monkeypatch):
    order = SimpleNamespace(id=uuid.uuid4(), document_version=3)
    document = SimpleNamespace(id=uuid.uuid4())
    client = SimpleNamespace(name="Cliente", email="same@example.com")
    representative = SimpleNamespace(name="Representante", email="SAME@example.com")
    monkeypatch.setattr(
        order_email_service,
        "_parties",
        AsyncMock(return_value=(client, representative)),
    )
    added = []
    db = SimpleNamespace(add=added.append)

    rows = await order_email_service._delivery_rows(db, order, document, 1)

    assert len(rows) == 1
    assert rows[0].recipient_kind == "client_and_representative"
    assert rows[0].recipient_email == "same@example.com"
    assert rows[0].status == "pending"


@pytest.mark.asyncio
async def test_delivery_rows_preserves_missing_address_without_blocking_other_recipient(monkeypatch):
    order = SimpleNamespace(id=uuid.uuid4(), document_version=1)
    document = SimpleNamespace(id=uuid.uuid4())
    client = SimpleNamespace(name="Cliente", email=None)
    representative = SimpleNamespace(name="Representante", email="rep@example.com")
    monkeypatch.setattr(
        order_email_service,
        "_parties",
        AsyncMock(return_value=(client, representative)),
    )
    added = []
    db = SimpleNamespace(add=added.append)

    rows = await order_email_service._delivery_rows(db, order, document, 1)

    assert len(rows) == 2
    assert {row.status for row in rows} == {"pending", "missing_address"}
    assert next(row for row in rows if row.status == "pending").recipient_email == "rep@example.com"


def test_verify_signature_accepts_svix_signature(monkeypatch):
    secret = b"test-webhook-secret"
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_" + base64.b64encode(secret).decode())
    raw = b'{"type":"email.delivered","data":{"email_id":"email_1"}}'
    event_id = "msg_123"
    timestamp = "1700000000"
    signed = f"{event_id}.{timestamp}.".encode() + raw
    signature = base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest()).decode()

    verify_signature(raw, event_id, timestamp, f"v1,{signature}", now=1700000000)


def test_verify_signature_rejects_tampering(monkeypatch):
    monkeypatch.setattr(
        settings,
        "RESEND_WEBHOOK_SECRET",
        "whsec_" + base64.b64encode(b"test-webhook-secret").decode(),
    )
    with pytest.raises(HTTPException) as exc:
        verify_signature(b"{}", "msg_123", "1700000000", "v1,invalid", now=1700000000)
    assert exc.value.status_code == 400


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _WebhookDb:
    def __init__(self, delivery):
        self.delivery = delivery
        self.calls = 0
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        self.calls += 1
        return _Result(None if self.calls == 1 else self.delivery)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_webhook_updates_delivery_and_is_recorded():
    delivery = SimpleNamespace(status="accepted", delivered_at=None, last_error="old")
    db = _WebhookDb(delivery)
    raw = json.dumps({"type": "email.delivered", "data": {"email_id": "email_1"}}).encode()

    assert await apply_event(db, "event_1", raw) is True
    assert delivery.status == "delivered"
    assert delivery.delivered_at is not None
    assert delivery.last_error is None
    assert db.added[0].event_id == "event_1"
    assert db.committed is True


class _DeliveryDb:
    def __init__(self, order, document):
        self.order = order
        self.document = document

    async def get(self, model, _identifier):
        if model is OrderDocument:
            return self.document
        return self.order


@pytest.mark.asyncio
async def test_worker_sends_pdf_with_reply_to_and_idempotency(monkeypatch):
    order = SimpleNamespace(code="PED-42", market_code="BR", locale="pt-BR")
    document = SimpleNamespace(storage_key="orders/file.pdf", market_code="BR", filename="PED-42.pdf")
    job = OrderEmailDelivery(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        recipient_kind="client",
        recipient_name="Cliente",
        recipient_email="client@example.com",
        idempotency_key="order-finalized/test",
    )
    monkeypatch.setattr(order_email_sender, "read_order_pdf", AsyncMock(return_value=PDF))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_REPLY_TO", "procgh@outlook.com")
    request = httpx.Request("POST", "https://api.resend.com/emails")
    response = httpx.Response(200, request=request, json={"id": "email_42"})
    client = SimpleNamespace(post=AsyncMock(return_value=response))

    message_id = await order_email_sender.deliver_job(client, _DeliveryDb(order, document), job)

    assert message_id == "email_42"
    kwargs = client.post.await_args.kwargs
    assert kwargs["headers"]["Idempotency-Key"] == "order-finalized/test"
    assert kwargs["json"]["reply_to"] == "procgh@outlook.com"
    assert kwargs["json"]["attachments"][0]["content"] == base64.b64encode(PDF).decode()
