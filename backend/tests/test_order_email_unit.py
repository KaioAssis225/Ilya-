import base64
import hashlib
import hmac
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.http_client import external_request as real_external_request
from app.core.resend_webhook import verify_resend_signature
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.services.order_email_jobs import recipient_is_allowed
from app.services.microsoft_graph_email import send_email as send_graph_email
from app.services.pdf_renderer import (
    PdfRendererUnavailable,
    PlaywrightPdfRenderer,
    _prepare_payload,
    get_pdf_renderer,
)
from app.services.resend_client import (
    PermanentEmailError,
    TemporaryEmailError,
    build_order_email,
    sanitize_attachment_filename,
    send_email,
)
from app.workers import order_email_sender
from app.workers.order_email_sender import (
    _process_delivery,
    _warn_missing_provider_config,
    retry_delay,
    retry_window_expired,
)


def _svix_signature(secret: bytes, event_id: str, timestamp: str, body: bytes) -> str:
    signed = f"{event_id}.{timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest()).decode()
    return f"v1,{digest}"


def test_svix_accepts_valid_and_one_of_multiple_signatures():
    key = b"webhook-test-key"
    secret = "whsec_" + base64.b64encode(key).decode()
    timestamp = str(int(time.time()))
    body = b'{"type":"email.delivered"}'
    valid = _svix_signature(key, "msg_1", timestamp, body)

    assert verify_resend_signature(secret, "msg_1", timestamp, body, valid)
    assert verify_resend_signature(
        secret,
        "msg_1",
        timestamp,
        body,
        f"v1,invalid {valid}",
    )


def test_svix_rejects_invalid_and_expired_signatures():
    key = b"webhook-test-key"
    secret = "whsec_" + base64.b64encode(key).decode()
    body = b"{}"
    current = str(int(time.time()))
    expired = str(int(time.time()) - 301)

    assert not verify_resend_signature(secret, "msg_1", current, body, "v1,invalid")
    assert not verify_resend_signature(
        secret,
        "msg_1",
        expired,
        body,
        _svix_signature(key, "msg_1", expired, body),
    )


@pytest.mark.parametrize(
    ("address", "allowlist", "expected"),
    [
        ("Pessoa@Example.com", "pessoa@example.com", True),
        ("pessoa@example.com", "@example.com", True),
        ("pessoa@other.com", "@example.com", False),
        ("pessoa@example.com", "", False),
    ],
)
def test_test_mode_allowlist_is_case_insensitive(address, allowlist, expected):
    assert recipient_is_allowed(address, allowlist) is expected


def test_backoff_caps_at_thirty_minutes_and_window_is_inclusive():
    assert retry_delay(1) == timedelta(seconds=30)
    assert retry_delay(2) == timedelta(seconds=60)
    assert retry_delay(20) == timedelta(minutes=30)
    started = datetime(2026, 10, 28, tzinfo=timezone.utc)
    assert not retry_window_expired(started, started + timedelta(hours=23, minutes=59))
    assert retry_window_expired(started, started + timedelta(hours=24))


@pytest.mark.asyncio
async def test_delivery_commit_error_rolls_back_and_records_pending(monkeypatch):
    document_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    document = OrderEmailDocument(
        id=document_id,
        order_id=uuid.uuid4(),
        market_code="BR",
        version=1,
        locale="pt-BR",
        status="ready",
        attempts=1,
        snapshot={"schema_version": 2, "order": {"code": "PED-1"}},
        storage_key="order-documents/order/v1.pdf",
    )
    delivery = OrderEmailDelivery(
        id=delivery_id,
        order_id=document.order_id,
        market_code="BR",
        document_id=document_id,
        recipient_roles=["client"],
        recipient_email="client@example.com",
        origin="finalization",
        status="processing",
        attempts=1,
        first_attempt_at=datetime.now(timezone.utc),
        idempotency_key=f"order-email/{delivery_id}",
    )
    reloaded = OrderEmailDelivery(
        id=delivery_id,
        order_id=document.order_id,
        market_code="BR",
        document_id=document_id,
        recipient_roles=["client"],
        recipient_email="client@example.com",
        origin="finalization",
        status="processing",
        attempts=1,
        first_attempt_at=delivery.first_attempt_at,
        idempotency_key=delivery.idempotency_key,
    )
    db = MagicMock()
    db.get = AsyncMock(side_effect=[document, reloaded])
    db.commit = AsyncMock(side_effect=[RuntimeError("commit failed"), None])
    db.rollback = AsyncMock()
    sender = AsyncMock(return_value="provider-message-1")
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(
        order_email_sender,
        "get_document",
        AsyncMock(return_value=b"%PDF"),
    )
    monkeypatch.setattr(order_email_sender, "apply_orphan_events", AsyncMock())

    await _process_delivery(db, delivery, sender)

    db.rollback.assert_awaited_once()
    db.get.assert_any_await(
        OrderEmailDelivery,
        delivery_id,
        populate_existing=True,
    )
    assert reloaded.status == "pending"
    assert reloaded.last_error == "provider_unavailable"
    assert reloaded.idempotency_key == delivery.idempotency_key


@pytest.mark.asyncio
async def test_missing_provider_warning_is_limited_to_ten_minutes(monkeypatch):
    result = MagicMock()
    result.scalar_one.return_value = 2
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    warning = MagicMock()
    started = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(order_email_sender, "_last_missing_provider_warning_at", None)
    monkeypatch.setattr(order_email_sender.logger, "warning", warning)

    await _warn_missing_provider_config(db, now=started)
    await _warn_missing_provider_config(
        db, now=started + timedelta(minutes=9, seconds=59)
    )
    await _warn_missing_provider_config(db, now=started + timedelta(minutes=10))

    assert warning.call_count == 2
    assert db.execute.await_count == 2


def test_attachment_filename_uses_only_order_code():
    assert sanitize_attachment_filename("PED/001") == "PED_001.pdf"
    content = build_order_email(
        {
            "schema_version": 2,
            "locale": "pt-PT",
            "order": {
                "code": "PED-9",
                "market_code": "EU",
                "locale": "pt-PT",
            },
            "client": {"name": "Nome Secreto"},
            "products": [],
            "category_labels": {},
        },
        b"%PDF-1.4\n%%EOF",
    )
    assert content["attachments"][0]["filename"] == "PED-9.pdf"
    assert "Nome Secreto" not in json.dumps(content, default=str)
    assert "IBTW" in content["subject"]


def test_invalid_order_email_mode_has_clear_configuration_error():
    with pytest.raises(ValidationError, match="ORDER_EMAIL_MODE deve ser off, test ou live"):
        Settings(
            SECRET_KEY="unit-test-secret",
            PASSWORD_PEPPER="unit-test-pepper",
            ORDER_EMAIL_MODE="unexpected",
        )


def test_invalid_order_email_provider_has_clear_configuration_error():
    with pytest.raises(
        ValidationError,
        match="ORDER_EMAIL_PROVIDER deve ser resend ou microsoft_graph",
    ):
        Settings(
            SECRET_KEY="unit-test-secret",
            PASSWORD_PEPPER="unit-test-pepper",
            ORDER_EMAIL_PROVIDER="smtp",
        )

    cfg = Settings(
        SECRET_KEY="unit-test-secret",
        PASSWORD_PEPPER="unit-test-pepper",
        ORDER_EMAIL_PROVIDER="Microsoft_Graph",
    )
    assert cfg.ORDER_EMAIL_PROVIDER == "microsoft_graph"


def test_order_email_pdf_renderer_validation_and_selection(monkeypatch):
    with pytest.raises(
        ValidationError,
        match="ORDER_EMAIL_PDF_RENDERER deve ser unavailable ou playwright",
    ):
        Settings(
            SECRET_KEY="unit-test-secret",
            PASSWORD_PEPPER="unit-test-pepper",
            ORDER_EMAIL_PDF_RENDERER="invalid",
        )

    cfg = Settings(
        SECRET_KEY="unit-test-secret",
        PASSWORD_PEPPER="unit-test-pepper",
        ORDER_EMAIL_PDF_RENDERER="Playwright",
    )
    assert cfg.ORDER_EMAIL_PDF_RENDERER == "playwright"

    monkeypatch.setattr(settings, "ORDER_EMAIL_PDF_RENDERER", "playwright")
    assert isinstance(get_pdf_renderer(), PlaywrightPdfRenderer)


@pytest.mark.asyncio
async def test_unavailable_pdf_renderer_raises_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ORDER_EMAIL_PDF_RENDERER", "unavailable")
    renderer = get_pdf_renderer()
    with pytest.raises(PdfRendererUnavailable):
        await renderer.render({"schema_version": 2})


@pytest.mark.asyncio
async def test_prepare_payload_resolves_local_photo_and_strips_photo_path(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    image_path = tmp_path / "produto.png"
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 40)).save(buf, format="PNG")
    image_path.write_bytes(buf.getvalue())

    warning_mock = MagicMock()
    monkeypatch.setattr("app.services.pdf_renderer.logger.warning", warning_mock)

    snapshot = {
        "schema_version": 2,
        "client": {"name": "Cliente Confidencial"},
        "products": [
            {
                "product_code": "P-OK",
                "photo_path": str(image_path),
                "thumbnail_url": None,
                "photo_url": None,
            },
            {
                "product_code": "P-AUSENTE",
                "photo_path": str(tmp_path / "inexistente.png"),
                "thumbnail_url": None,
                "photo_url": None,
            },
        ],
    }

    payload = await _prepare_payload(snapshot)
    assert "photo_path" not in payload["products"][0]
    assert "photo_path" not in payload["products"][1]
    assert payload["products"][0]["thumbnail_url"].startswith("data:image/png;base64,")
    assert payload["products"][1]["thumbnail_url"] is None
    warning_mock.assert_called_once()
    logged_text = " ".join(str(arg) for arg in warning_mock.call_args.args)
    assert "Cliente Confidencial" not in logged_text
    assert "inexistente.png" not in logged_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type", "code"),
    [
        (401, TemporaryEmailError, "provider_auth"),
        (409, TemporaryEmailError, "provider_unavailable"),
        (429, TemporaryEmailError, "provider_unavailable"),
        (503, TemporaryEmailError, "provider_unavailable"),
        (422, PermanentEmailError, "provider_rejected"),
    ],
)
async def test_resend_classifies_http_errors_with_mock_transport(
    monkeypatch, status_code, error_type, code
):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, json={"provider": "private"})
    )
    client = httpx.AsyncClient(transport=transport)

    async def request(method, url, **kwargs):
        return await real_external_request(method, url, client=client, **kwargs)

    monkeypatch.setattr("app.services.resend_client.external_request", request)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
    with pytest.raises(error_type) as caught:
        await send_email(
            idempotency_key="order-email/1",
            to="recipient@example.com",
            subject="Pedido PED-1",
            text="texto",
            html="<p>texto</p>",
            attachments=[{"filename": "PED-1.pdf", "content": b"%PDF"}],
        )
    assert caught.value.code == code
    assert "private" not in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_resend_success_returns_provider_id_and_encodes_attachment(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "resend-message-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def request(method, url, **kwargs):
        return await real_external_request(method, url, client=client, **kwargs)

    monkeypatch.setattr("app.services.resend_client.external_request", request)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
    result = await send_email(
        idempotency_key="order-email/1",
        to="recipient@example.com",
        subject="Pedido PED-1",
        text="texto",
        html="<p>texto</p>",
        attachments=[{"filename": "PED-1.pdf", "content": b"%PDF"}],
    )
    assert result == "resend-message-1"
    assert captured["attachments"][0]["content"] == base64.b64encode(b"%PDF").decode()
    await client.aclose()


@pytest.mark.asyncio
async def test_graph_success_refreshes_token_and_sends_pdf_with_reply_to(monkeypatch):
    requests = []

    async def request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        if "oauth2/v2.0/token" in url:
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(202)

    monkeypatch.setattr(
        "app.services.microsoft_graph_email.external_request",
        request,
    )
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "MICROSOFT_GRAPH_TENANT", "consumers")
    monkeypatch.setattr(
        settings,
        "MICROSOFT_GRAPH_SENDER_EMAIL",
        "procgh@outlook.com",
    )
    monkeypatch.setattr(
        settings,
        "ORDER_EMAIL_FROM",
        "Ilya Pedidos <procgh@outlook.com>",
    )
    monkeypatch.setattr(settings, "ORDER_EMAIL_REPLY_TO", "procgh@outlook.com")

    result = await send_graph_email(
        idempotency_key="order-email/1",
        to="recipient@example.com",
        subject="Pedido PED-1",
        text="texto",
        html="<p>texto</p>",
        attachments=[{"filename": "PED-1.pdf", "content": b"%PDF"}],
    )

    assert result == "graph-accepted:" + hashlib.sha256(
        b"order-email/1"
    ).hexdigest()
    assert len(requests) == 2
    token_method, token_url, token_kwargs = requests[0]
    assert token_method == "post"
    assert token_url.endswith("/consumers/oauth2/v2.0/token")
    assert token_kwargs["data"]["refresh_token"] == "refresh-token"
    assert token_kwargs["data"]["scope"].endswith("/Mail.Send")

    send_method, send_url, send_kwargs = requests[1]
    assert send_method == "post"
    assert send_url == "https://graph.microsoft.com/v1.0/me/sendMail"
    assert send_kwargs["headers"]["Authorization"] == "Bearer access-token"
    message = send_kwargs["json"]["message"]
    assert message["from"]["emailAddress"] == {
        "address": "procgh@outlook.com",
        "name": "Ilya Pedidos",
    }
    assert message["toRecipients"][0]["emailAddress"]["address"] == (
        "recipient@example.com"
    )
    assert message["replyTo"][0]["emailAddress"]["address"] == (
        "procgh@outlook.com"
    )
    assert message["attachments"][0]["contentBytes"] == base64.b64encode(
        b"%PDF"
    ).decode()
    assert message["internetMessageHeaders"][0]["value"] == "order-email/1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type", "code"),
    [
        (401, TemporaryEmailError, "provider_auth"),
        (429, TemporaryEmailError, "provider_unavailable"),
        (503, TemporaryEmailError, "provider_unavailable"),
        (422, PermanentEmailError, "provider_rejected"),
    ],
)
async def test_graph_classifies_send_errors(
    monkeypatch, status_code, error_type, code
):
    async def request(method, url, **kwargs):
        if "oauth2/v2.0/token" in url:
            return httpx.Response(200, json={"access_token": "access-token"})
        return httpx.Response(status_code)

    monkeypatch.setattr(
        "app.services.microsoft_graph_email.external_request",
        request,
    )
    with pytest.raises(error_type) as caught:
        await send_graph_email(
            idempotency_key="order-email/1",
            to="recipient@example.com",
            subject="Pedido PED-1",
            text="texto",
            html="<p>texto</p>",
            attachments=[{"filename": "PED-1.pdf", "content": b"%PDF"}],
        )
    assert caught.value.code == code


def test_worker_selects_graph_provider_only_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "ORDER_EMAIL_PROVIDER", "microsoft_graph")
    monkeypatch.setattr(
        order_email_sender,
        "microsoft_graph_configured",
        lambda: True,
    )
    assert order_email_sender._provider_configured()
    assert order_email_sender._provider_sender() is order_email_sender.send_graph_email
