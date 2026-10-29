import hashlib
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.order_documents import get_document
from app.core.security import create_access_token
from app.models.market import PriceList
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.user import UserRole
from app.services.pdf_renderer import PdfRendererUnavailable, PlaywrightPdfRenderer
from app.workers.order_email_sender import process_due
from tests.factories import make_client, make_user, make_user_market
from tests.factories.orders import make_order, make_order_item


pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.pdf_render]


async def _price_list(db, market: str):
    return (
        await db.execute(
            select(PriceList)
            .where(PriceList.market_code == market)
            .order_by(PriceList.code)
            .limit(1)
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()


def _configure_local_email_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "ORDER_EMAIL_PDF_RENDERER", "playwright")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
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


async def _ensure_chromium_available(snapshot: dict) -> None:
    try:
        await PlaywrightPdfRenderer().render(snapshot)
    except PdfRendererUnavailable as exc:
        pytest.skip(f"Playwright/Chromium indisponível neste ambiente: {exc}")


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_finalize_renders_real_pdf_and_manual_resend_reuses_document(
    client, db_session, monkeypatch, tmp_path, market
):
    _configure_local_email_env(monkeypatch, tmp_path)

    user = await make_user(db_session, role=UserRole.admin, home_market=market)
    await make_user_market(db_session, user, market_code=market, role="admin")
    customer = await make_client(
        db_session, await _price_list(db_session, market), market_code=market
    )
    customer.email = f"cliente-{market.lower()}@example.com"
    order = await make_order(db_session, customer, user.id, market_code=market)
    await make_order_item(db_session, order, description="Poltrona de teste")
    await db_session.flush()

    token = create_access_token(user.id, "admin", user.auth_version, market)
    headers = {"Authorization": f"Bearer {token}"}

    finalize_res = await client.post(
        f"/api/v1/orders/{order.id}/finalize",
        json={},
        headers=headers,
    )
    assert finalize_res.status_code == 200, finalize_res.text

    document = (
        await db_session.execute(
            select(OrderEmailDocument).where(OrderEmailDocument.order_id == order.id)
        )
    ).scalar_one()
    assert document.snapshot["schema_version"] == 2

    await _ensure_chromium_available(document.snapshot)

    sent_messages = []

    async def fake_sender(**kwargs):
        sent_messages.append(kwargs)
        return f"provider-msg-{len(sent_messages)}"

    await process_due(
        db_session,
        renderer=PlaywrightPdfRenderer(),
        sender=fake_sender,
    )
    await db_session.refresh(document)

    assert document.status == "ready"
    assert document.storage_key is not None
    assert document.sha256 is not None
    assert document.size_bytes and document.size_bytes > 0

    stored_pdf = await get_document(document.market_code, document.storage_key)
    assert stored_pdf.startswith(b"%PDF")
    assert hashlib.sha256(stored_pdf).hexdigest() == document.sha256
    assert len(stored_pdf) == document.size_bytes

    delivery = (
        await db_session.execute(
            select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order.id)
        )
    ).scalar_one()
    assert delivery.status == "accepted"
    assert len(sent_messages) == 1
    assert sent_messages[0]["attachments"][0]["content"] == stored_pdf

    original_doc_id = document.id
    original_sha256 = document.sha256
    original_storage_key = document.storage_key

    resend_res = await client.post(
        f"/api/v1/orders/{order.id}/emails/resend",
        json={"delivery_id": str(delivery.id)},
        headers=headers,
    )
    assert resend_res.status_code == 201, resend_res.text
    resent_id = uuid.UUID(resend_res.json()["id"])

    await process_due(
        db_session,
        renderer=PlaywrightPdfRenderer(),
        sender=fake_sender,
    )

    resent = await db_session.get(
        OrderEmailDelivery, resent_id, populate_existing=True
    )
    await db_session.refresh(document)

    assert resent is not None
    assert resent.status == "accepted"
    assert resent.document_id == original_doc_id
    assert document.id == original_doc_id
    assert document.sha256 == original_sha256
    assert document.storage_key == original_storage_key
    assert len(sent_messages) == 2
