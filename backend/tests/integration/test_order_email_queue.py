import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.order_documents import OrderDocumentStorageError, put_document
from app.core.security import create_access_token
from app.models.market import PriceList
from app.models.optional_category import OptionalCategory
from app.models.optional_color import OptionalColor
from app.models.order import OrderItem
from app.models.order_email import OrderEmailDelivery, OrderEmailDocument
from app.models.product import Product, ProductSetComponent
from app.models.user import UserRole
from app.services.order_email_jobs import enqueue_order_emails
from app.services.pdf_renderer import PdfRendererUnavailable
from app.services.resend_client import TemporaryEmailError
from app.workers.order_email_sender import claim_next_delivery, process_due
from tests.factories import make_client, make_representative, make_user, make_user_market
from tests.factories.orders import make_order, make_order_item


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"


def _is_number(value):
    """A API serializa Decimal como string ("100.00"); o snapshot espelha a API."""
    if isinstance(value, bool):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


class _Renderer:
    async def render(self, snapshot):
        return _PDF


async def _price_list(db, market="BR"):
    return (
        await db.execute(
            select(PriceList)
            .where(PriceList.market_code == market)
            .order_by(PriceList.code)
            .limit(1)
            .execution_options(skip_market_scope=True)
        )
    ).scalar_one()


async def _order(db, *, market="BR", client_email="client@example.com", rep_email=None):
    owner = await make_user(db, role=UserRole.admin, home_market=market)
    await make_user_market(db, owner, market_code=market, role="admin")
    client = await make_client(db, await _price_list(db, market), market_code=market)
    client.email = client_email
    order = await make_order(db, client, owner.id, market_code=market)
    await make_order_item(db, order)
    if rep_email is not None:
        rep = await make_representative(db, market_code=market)
        rep.email = rep_email
        order.rep_id = rep.id
    await db.flush()
    return order, owner


async def test_off_does_not_enqueue_or_query_side_effects(db_session, monkeypatch):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "off")

    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    assert (await db_session.execute(select(func.count()).select_from(OrderEmailDocument))).scalar_one() == 0


async def test_finalize_in_off_mode_keeps_queue_empty(client, db_session, monkeypatch):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "off")
    token = create_access_token(owner.id, "admin", owner.auth_version, order.market_code)

    response = await client.post(
        f"/api/v1/orders/{order.id}/finalize",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_finalized"] is True
    assert (await db_session.execute(select(func.count()).select_from(OrderEmailDocument))).scalar_one() == 0


async def test_enqueue_is_idempotent_and_merges_equal_recipients(db_session, monkeypatch):
    order, owner = await _order(
        db_session,
        client_email="Shared@Example.com",
        rep_email="shared@example.com",
    )
    item_code = (
        await db_session.execute(
            select(OrderItem.product_code)
            .where(OrderItem.order_id == order.id)
            .limit(1)
        )
    ).scalar_one()
    product = (
        await db_session.execute(
            select(Product).where(
                Product.market_code == order.market_code,
                Product.product_code == item_code,
            )
        )
    ).scalar_one()
    product.is_set = True
    product.photo_path = "object://products/foto-conjunto.jpg"

    db_session.add(
        OptionalCategory(
            market_code=order.market_code,
            code="corda_v2",
            name="Corda Náutica",
        )
    )
    db_session.add(
        OptionalCategory(
            market_code="EU",
            code="categoria_eu_isolada",
            name="Categoria EU",
        )
    )
    opt_color = OptionalColor(
        market_code=order.market_code,
        category="corda_v2",
        color_name="Terracota",
        brand="ILYA",
    )
    db_session.add(opt_color)
    await db_session.flush()
    db_session.add(
        ProductSetComponent(
            set_id=product.id,
            description="Módulo Direito",
            is_circular=False,
            altura=75,
            largura=180,
            profundidade=90,
            qty=2,
            optionals=[opt_color],
        )
    )
    await db_session.flush()

    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    documents = (await db_session.execute(select(OrderEmailDocument))).scalars().all()
    deliveries = (await db_session.execute(select(OrderEmailDelivery))).scalars().all()
    assert len(documents) == 1
    assert len(deliveries) == 1
    assert deliveries[0].recipient_roles == ["client", "representative"]
    assert deliveries[0].recipient_email == "shared@example.com"

    snapshot = documents[0].snapshot
    assert snapshot["schema_version"] == 2
    assert "history" not in snapshot["order"]
    assert _is_number(snapshot["order"]["total_value"])
    assert _is_number(snapshot["order"]["total_ipi"])
    assert _is_number(snapshot["order"]["total_with_ipi"])
    assert _is_number(snapshot["order"]["items"][0]["unit_price"])
    assert _is_number(snapshot["order"]["items"][0]["discount"])
    assert _is_number(snapshot["order"]["items"][0]["ipi_rate"])
    assert _is_number(snapshot["order"]["items"][0]["ipi_value"])
    assert _is_number(snapshot["client"]["max_discount"])
    assert _is_number(snapshot["representative"]["max_discount"])
    assert snapshot["category_labels"]["corda_v2"] == "Corda Náutica"
    assert "categoria_eu_isolada" not in snapshot["category_labels"]

    prod_snap = next(
        p for p in snapshot["products"] if p["product_code"] == item_code
    )
    assert prod_snap["is_set"] is True
    assert prod_snap["type"] == product.type
    assert prod_snap["photo_path"] == "object://products/foto-conjunto.jpg"
    assert prod_snap["thumbnail_url"] is None
    assert prod_snap["photo_url"] is None
    assert "price" not in prod_snap
    assert "price_lojista" not in prod_snap
    assert "price_corporativo" not in prod_snap
    assert len(prod_snap["components"]) == 1
    comp_snap = prod_snap["components"][0]
    assert comp_snap["description"] == "Módulo Direito"
    assert comp_snap["qty"] == 2
    assert _is_number(comp_snap["largura"])
    assert _is_number(comp_snap["profundidade"])
    assert _is_number(comp_snap["altura"])
    assert len(comp_snap["optionals"]) == 1
    assert comp_snap["optionals"][0]["category"] == "corda_v2"
    assert comp_snap["optionals"][0]["color_name"] == "Terracota"


async def test_document_retry_window_starts_on_first_attempt(
    db_session, monkeypatch, tmp_path
):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "")
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)
    document = (await db_session.execute(select(OrderEmailDocument))).scalar_one()
    document.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.commit()

    class UnavailableRenderer:
        async def render(self, snapshot):
            raise PdfRendererUnavailable

    await process_due(db_session, renderer=UnavailableRenderer())
    await db_session.refresh(document)
    delivery = (await db_session.execute(select(OrderEmailDelivery))).scalar_one()

    assert document.status == "pending"
    assert document.first_attempt_at is not None
    assert document.first_attempt_at > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert delivery.status == "pending"


async def test_invalid_recipient_is_blocked_without_blocking_other(db_session, monkeypatch):
    order, owner = await _order(
        db_session,
        client_email="invalid-address",
        rep_email="representative@example.com",
    )
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    deliveries = (await db_session.execute(
        select(OrderEmailDelivery).order_by(OrderEmailDelivery.recipient_roles)
    )).scalars().all()
    assert {row.status for row in deliveries} == {"blocked", "pending"}
    blocked = next(row for row in deliveries if row.status == "blocked")
    assert blocked.last_error == "invalid_recipient"


async def test_enqueue_rolls_back_with_calling_transaction(db_session, monkeypatch):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    with pytest.raises(RuntimeError):
        async with db_session.begin_nested():
            await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)
            raise RuntimeError("rollback")

    assert (await db_session.execute(select(func.count()).select_from(OrderEmailDocument))).scalar_one() == 0


async def test_expired_delivery_lease_is_reclaimed_but_current_lease_is_not(db_session):
    order, owner = await _order(db_session)
    document = OrderEmailDocument(
        order_id=order.id,
        market_code=order.market_code,
        version=order.document_version,
        locale=order.locale,
        status="ready",
        attempts=1,
        snapshot={"schema_version": 2},
        storage_key="order-documents/00000000-0000-0000-0000-000000000000/v1-0000000000000000.pdf",
    )
    db_session.add(document)
    await db_session.flush()
    delivery = OrderEmailDelivery(
        order_id=order.id,
        market_code=order.market_code,
        document_id=document.id,
        recipient_roles=["client"],
        recipient_email="client@example.com",
        origin="finalization",
        requested_by_user_id=owner.id,
        status="processing",
        attempts=1,
        next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        idempotency_key=f"order-email/{uuid.uuid4()}",
    )
    db_session.add(delivery)
    await db_session.flush()
    now = datetime.now(timezone.utc)

    claimed = await claim_next_delivery(db_session, now)

    assert claimed.id == delivery.id and claimed.attempts == 2
    assert await claim_next_delivery(db_session, now) is None


async def test_provider_outage_backs_off_then_succeeds(db_session, monkeypatch, tmp_path):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    async def unavailable(**kwargs):
        raise TemporaryEmailError("provider_unavailable")

    assert await process_due(db_session, renderer=_Renderer(), sender=unavailable) == 2
    delivery = (await db_session.execute(select(OrderEmailDelivery))).scalar_one()
    assert delivery.status == "pending"
    assert delivery.last_error == "provider_unavailable"
    assert delivery.next_attempt_at > datetime.now(timezone.utc)

    delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    async def success(**kwargs):
        return "provider-message-1"

    assert await process_due(db_session, renderer=_Renderer(), sender=success) == 1
    assert delivery.status == "accepted"
    assert delivery.provider_message_id == "provider-message-1"


async def test_temporary_failure_after_24_hours_needs_review(db_session, monkeypatch, tmp_path):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    async def unavailable(**kwargs):
        raise TemporaryEmailError("provider_unavailable")

    await process_due(db_session, renderer=_Renderer(), sender=unavailable)
    delivery = (await db_session.execute(select(OrderEmailDelivery))).scalar_one()
    delivery.first_attempt_at = datetime.now(timezone.utc) - timedelta(hours=24)
    delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await process_due(db_session, renderer=_Renderer(), sender=unavailable)

    assert delivery.status == "needs_review"
    assert delivery.next_attempt_at is None


async def test_test_mode_skips_outside_allowlist_and_live_sends(
    db_session, monkeypatch, tmp_path
):
    order, owner = await _order(db_session, client_email="client@example.com")
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "test")
    monkeypatch.setattr(settings, "ORDER_EMAIL_TEST_ALLOWLIST", "@allowed.example")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "Ilya <test@example.com>")
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)
    calls = 0

    async def sender(**kwargs):
        nonlocal calls
        calls += 1
        return "provider-message"

    await process_due(db_session, renderer=_Renderer(), sender=sender)
    delivery = (await db_session.execute(select(OrderEmailDelivery))).scalar_one()
    assert delivery.status == "skipped"
    assert delivery.last_error == "not_in_allowlist"
    assert calls == 0

    order2, owner2 = await _order(db_session, client_email="other@example.com")
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    await enqueue_order_emails(db_session, order2, requested_by_user_id=owner2.id)
    await process_due(db_session, renderer=_Renderer(), sender=sender)
    delivery2 = (await db_session.execute(
        select(OrderEmailDelivery).where(OrderEmailDelivery.order_id == order2.id)
    )).scalar_one()
    assert delivery2.status == "accepted"
    assert calls == 1


async def test_missing_provider_configuration_leaves_delivery_pending(
    db_session, monkeypatch, tmp_path
):
    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "ORDER_EMAIL_FROM", "")
    monkeypatch.setattr(settings, "ORDER_EMAIL_LOCAL_DIR", str(tmp_path))
    await enqueue_order_emails(db_session, order, requested_by_user_id=owner.id)

    await process_due(db_session, renderer=_Renderer())

    delivery = (await db_session.execute(select(OrderEmailDelivery))).scalar_one()
    assert delivery.status == "pending"
    assert delivery.attempts == 0


async def test_document_storage_never_falls_back_between_market_buckets(monkeypatch):
    from app.core import order_documents

    calls = []

    class Storage:
        def __init__(self, market):
            self.market = market

        def put_object(self, **kwargs):
            calls.append((self.market, kwargs["Bucket"], kwargs["Key"]))

    for name, value in {
        "OBJECT_STORAGE_ENDPOINT": "https://br.example",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "br-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "br-secret",
        "OBJECT_STORAGE_BUCKET": "br-bucket",
        "OBJECT_STORAGE_EU_ENDPOINT": "https://eu.example",
        "OBJECT_STORAGE_EU_ACCESS_KEY_ID": "eu-key",
        "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY": "eu-secret",
        "OBJECT_STORAGE_EU_BUCKET": "eu-bucket",
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(order_documents, "_object_storage_client", lambda: Storage("BR"))
    monkeypatch.setattr(order_documents, "_eu_object_storage_client", lambda: Storage("EU"))

    await put_document("BR", uuid.uuid4(), 1, _PDF)
    await put_document("EU", uuid.uuid4(), 1, _PDF)

    assert [(market, bucket) for market, bucket, _ in calls] == [
        ("BR", "br-bucket"),
        ("EU", "eu-bucket"),
    ]

    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_ENDPOINT", "")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_ACCESS_KEY_ID", "")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", "")
    with pytest.raises(OrderDocumentStorageError) as caught:
        await put_document("EU", uuid.uuid4(), 1, _PDF)
    assert caught.value.code == "storage_not_configured"


async def test_enqueue_bug_does_not_prevent_finalization(client, db_session, monkeypatch):
    from app.api.routers import orders as orders_router

    order, owner = await _order(db_session)
    monkeypatch.setattr(settings, "ORDER_EMAIL_MODE", "live")

    async def broken(*args, **kwargs):
        raise RuntimeError("email queue bug")

    monkeypatch.setattr(orders_router, "enqueue_order_emails", broken)
    token = create_access_token(owner.id, "admin", owner.auth_version, order.market_code)
    response = await client.post(
        f"/api/v1/orders/{order.id}/finalize",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_finalized"] is True
    assert (await db_session.execute(select(func.count()).select_from(OrderEmailDocument))).scalar_one() == 0
