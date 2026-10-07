"""Assinatura vinculada aos termos, ao titular e ao ciclo imutável do pedido."""

import asyncio
import copy
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi import Response
from sqlalchemy.sql import Select

from app.api.routers import orders
from app.models.user import UserRole
from app.schemas.order import OrderUpdate


def _order():
    item = SimpleNamespace(
        id=uuid.uuid4(), product_code="MESA-01", description="Mesa",
        is_circular=False, altura=Decimal("70.00"), largura=Decimal("80.00"),
        profundidade=Decimal("50.00"), qty=1, unit_price=Decimal("100.00"),
        discount=Decimal("0.00"), ipi_rate=Decimal("5.00"),
        ipi_value=Decimal("5.00"), tax_label="IPI", currency="BRL",
        observacao=None, opt_categories={"cor": "azul"},
    )
    return SimpleNamespace(
        id=uuid.uuid4(), document_version=1, market_code="BR", code="PED-0001",
        orc_id="ORC-0001", client_id=uuid.uuid4(), rep_id=None,
        price_list_code="lojista", currency="BRL", locale="pt-BR",
        is_finalized=False, is_cancelled=False, external_code=None,
        total_value=Decimal("100.00"), total_ipi=Decimal("5.00"),
        total_with_ipi=Decimal("105.00"), notes="Condição original",
        items=[item], rep_signature=None, client_signature=None,
    )


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, *selected):
        self.selected = iter(selected)
        self.added = []
        self.commits = 0
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(next(self.selected) if isinstance(statement, Select) else None)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def test_canonical_hash_changes_with_every_material_term():
    original = _order()
    baseline = orders._order_document_hash(original)
    mutations = (
        lambda o: setattr(o, "notes", "Outra condição"),
        lambda o: setattr(o.items[0], "qty", 2),
        lambda o: setattr(o.items[0], "discount", Decimal("1.00")),
        lambda o: setattr(o.items[0], "ipi_rate", Decimal("6.00")),
        lambda o: setattr(o.items[0], "observacao", "Acabamento especial"),
        lambda o: setattr(o, "document_version", 2),
    )
    for mutate in mutations:
        changed = copy.deepcopy(original)
        mutate(changed)
        assert orders._order_document_hash(changed) != baseline


def test_signed_order_cannot_be_edited():
    order = _order()
    order.rep_signature = "legacy-signature"
    session = _Session(order)
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
    principal = SimpleNamespace(code="BR")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(orders.update_order(
            order.id, OrderUpdate(notes="Alteração"), db=session,
            current_user=actor, principal=principal,
        ))
    assert rejected.value.status_code == 409
    assert session.statements[0]._for_update_arg is not None
    assert session.commits == 0
    assert order.notes == "Condição original"


def test_signed_order_cannot_be_finalized_cancelled_or_deleted():
    order = _order()
    order.client_signature = "legacy-signature"
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
    operations = (
        lambda session: orders.finalize_order(
            order.id, orders.FinalizePayload(), db=session, current_user=admin,
        ),
        lambda session: orders.cancel_order(
            order.id, orders.CancelPayload(), db=session, current_user=admin,
        ),
        lambda session: orders.delete_order(order.id, db=session, current_user=admin, principal=SimpleNamespace(code="BR")),
    )
    for operation in operations:
        session = _Session(order)
        with pytest.raises(HTTPException) as rejected:
            asyncio.run(operation(session))
        assert rejected.value.status_code == 409
        assert session.commits == 0


def test_operator_cannot_submit_client_signature(monkeypatch):
    monkeypatch.setattr(orders, "_require_electronic_signatures_enabled", lambda: None)
    order = _order()
    session = _Session(order)
    representative = SimpleNamespace(
        id=uuid.uuid4(), role=UserRole.representante, linked_id=None,
    )
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(orders.sign_client(
            order.id, orders.SignPayload(signature="data:image/png;base64,AA=="),
            db=session, current_user=representative,
        ))
    assert rejected.value.status_code == 403
    assert not session.statements


def test_client_signature_records_hash_version_and_actor(monkeypatch):
    monkeypatch.setattr(orders, "_require_electronic_signatures_enabled", lambda: None)

    async def touch(*_args):
        return datetime.now(timezone.utc)

    monkeypatch.setattr(orders, "touch_client_activity", touch)
    order = _order()
    session = _Session(order)
    client = SimpleNamespace(id=uuid.uuid4(), role=UserRole.cliente, linked_id=order.client_id)
    signature = "data:image/png;base64,AA=="
    asyncio.run(orders.sign_client(
        order.id, orders.SignPayload(signature=signature), db=session, current_user=client,
    ))
    evidence = session.added[0]
    assert evidence.document_hash == orders._order_document_hash(order)
    assert evidence.document_version == order.document_version
    assert evidence.submitted_by_user_id == client.id
    assert evidence.method == "authenticated"
    assert evidence.verification_status == "captured"
    assert session.commits == 1


def test_expired_consumed_or_unsent_invitation_is_invalid():
    base = SimpleNamespace(
        consumed_at=None, revoked_at=None, sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert orders._invitation_is_valid(base)
    for attr, value in (
        ("consumed_at", datetime.now(timezone.utc)),
        ("revoked_at", datetime.now(timezone.utc)),
        ("sent_at", None),
        ("expires_at", datetime.now(timezone.utc) - timedelta(seconds=1)),
    ):
        invalid = copy.copy(base)
        setattr(invalid, attr, value)
        assert not orders._invitation_is_valid(invalid)


def test_signature_invitation_is_emailed_without_returning_token(monkeypatch):
    monkeypatch.setattr(orders, "_require_electronic_signatures_enabled", lambda: None)
    monkeypatch.setattr(orders, "invitation_delivery_ready", lambda: True)

    async def touch(*_args):
        return datetime.now(timezone.utc)

    delivered = []

    async def send(recipient, code, token):
        delivered.append((recipient, code, token))

    monkeypatch.setattr(orders, "touch_client_activity", touch)
    monkeypatch.setattr(orders, "send_signature_invitation", send)
    order = _order()
    client = SimpleNamespace(id=order.client_id, email="titular@example.com")
    session = _Session(order, client)
    admin_id = uuid.uuid4()
    admin = SimpleNamespace(id=admin_id, role=UserRole.admin)
    principal = SimpleNamespace(code="BR")
    body = orders.SignatureInviteIssue(
        confirmed_email="titular@example.com", verification_method="phone_callback",
    )
    result = asyncio.run(orders.generate_sign_token.__wrapped__(
        request=None, response=Response(), order_id=order.id, body=body,
        db=session, current_user=admin, principal=principal,
    ))
    assert result == {"status": "sent", "recipient_email": "titular@example.com"}
    assert len(delivered) == 1
    assert delivered[0][2] not in str(result)
    invitation = session.added[0]
    assert invitation.document_hash == orders._order_document_hash(order)
    assert invitation.document_version == order.document_version
    assert invitation.verified_by_user_id == admin_id
    assert invitation.sent_at is not None
    assert session.commits == 2


def test_token_for_previous_document_version_is_revoked(monkeypatch):
    monkeypatch.setattr(orders, "_require_electronic_signatures_enabled", lambda: None)
    order = _order()
    signed_hash = orders._order_document_hash(order)
    order.document_version = 2
    invitation = SimpleNamespace(
        order_id=order.id, document_version=1, document_hash=signed_hash,
        sent_at=datetime.now(timezone.utc), consumed_at=None, revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session = _Session(invitation, order)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(orders.verify_sign_token.__wrapped__(
            request=None, response=Response(),
            body=orders.VerifySignTokenPayload(token="x" * 32), db=session,
        ))
    assert rejected.value.status_code == 400
    assert invitation.revoked_at is not None
    assert session.commits == 1


def test_revision_uses_new_order_flow_without_copying_signatures(monkeypatch):
    source = _order()
    source.rep_signature = "legacy-signature"
    source.revision_number = 1
    session = _Session(source)
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
    principal = SimpleNamespace(code="BR")
    captured = []

    async def create(payload, db, current_user, market_principal):
        captured.append(payload)
        assert db is session and current_user is admin and market_principal is principal
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(orders, "create_order", create)
    result = asyncio.run(orders.create_order_revision(
        source.id, db=session, current_user=admin, principal=principal,
    ))
    assert result.id
    assert captured[0].supersedes_order_id == source.id
    assert captured[0].items[0].product_code == source.items[0].product_code
    assert captured[0].items[0].qty == source.items[0].qty
    assert "signature" not in captured[0].model_dump_json()
