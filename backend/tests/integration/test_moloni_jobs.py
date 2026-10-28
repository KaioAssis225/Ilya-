"""Fila de exportação Moloni: claim por job, falha isolada e conexão única.

JOB-01  claim marca o job como `processing` com lease; não é reclamado
        enquanto o lease vale.
JOB-02  lease vencido (worker morreu no meio) volta a ser reclamado.
JOB-03  falha num job não desfaz a entrega anterior e não grava token.
CONN-01 duas conexões ativas: o exportador recusa escolher.
CONN-02 conectar outra empresa desativa a conexão anterior.
ENQ-01  enqueue manual: ID malformado → 422, inexistente → 404, pedido BR ou
        não finalizado → 422, EU finalizado → 202 com um job pendente.

PostgreSQL real; cada teste roda dentro da transação revertida da fixture.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.moloni import MoloniConnection, MoloniExportJob, MoloniOAuthState
from app.services.moloni_exporter import MoloniError, active_moloni_connection
from app.workers.moloni_sender import claim_next_job, process_due_jobs
from tests.factories import make_client, make_platform_permission, make_price_list, make_user
from tests.factories.orders import make_order

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _job(db: AsyncSession, **fields) -> MoloniExportJob:
    prices = await make_price_list(db, market_code="EU")
    client = await make_client(db, prices, market_code="EU")
    owner = await make_user(db)
    order = await make_order(db, client, owner.id)
    job = MoloniExportJob(order_id=order.id, status="pending", **fields)
    db.add(job)
    await db.flush()
    return job


def _connection(company_id: int, *, active: bool = True) -> MoloniConnection:
    return MoloniConnection(
        company_id=company_id,
        access_token_ciphertext="cifrado",
        refresh_token_ciphertext="cifrado",
        is_active=active,
    )


async def test_job01_claim_sets_processing_lease_and_blocks_reclaim(db_session: AsyncSession) -> None:
    job = await _job(db_session)
    now = datetime.now(timezone.utc)

    claimed = await claim_next_job(db_session, now)

    assert claimed is not None and claimed.id == job.id
    assert claimed.status == "processing"
    assert claimed.attempts == 1
    assert claimed.next_attempt_at > now
    assert await claim_next_job(db_session, now) is None


async def test_job02_expired_lease_is_reclaimed(db_session: AsyncSession) -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    job = await _job(db_session, attempts=1)
    job.status = "processing"
    job.next_attempt_at = past
    await db_session.flush()

    claimed = await claim_next_job(db_session, datetime.now(timezone.utc))

    assert claimed is not None and claimed.id == job.id
    assert claimed.attempts == 2


async def test_job03_failure_keeps_previous_delivery_and_redacts_token(db_session: AsyncSession) -> None:
    first = await _job(db_session)
    second = await _job(db_session)
    first.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    await db_session.flush()

    async def deliver(_db, job):
        if job.id == first.id:
            return 101
        raise RuntimeError(
            "Client error '400 Bad Request' for url "
            "'https://api.moloni.pt/v1/estimates/insert/?access_token=SEGREDO123&json=true'"
        )

    processed = await process_due_jobs(db_session, deliver=deliver)

    assert processed == 2
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert (first.status, first.moloni_document_id) == ("delivered", 101)
    assert second.status == "pending"
    assert second.attempts == 1
    assert "SEGREDO123" not in second.last_error
    assert "access_token=[REDACTED]" in second.last_error
    assert second.next_attempt_at > datetime.now(timezone.utc)


async def test_conn01_exporter_refuses_ambiguous_active_connection(db_session: AsyncSession) -> None:
    db_session.add_all([_connection(9001), _connection(9002)])
    await db_session.flush()

    with pytest.raises(MoloniError):
        await active_moloni_connection(db_session)


async def test_conn02_connecting_another_company_deactivates_previous(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    from app.api.routers import moloni

    previous = _connection(9101)
    user = await make_user(db_session)
    state = "estado-opaco-de-teste-" + "x" * 20
    db_session.add_all([
        previous,
        MoloniOAuthState(
            state=state,
            company_id=9102,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    ])
    await db_session.flush()

    class _Response:
        def raise_for_status(self): return None
        def json(self): return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

    class _Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return None
        async def get(self, *_, **__): return _Response()

    for name, value in {
        "MOLONI_CLIENT_ID": "id",
        "MOLONI_CLIENT_SECRET": "secret",
        "MOLONI_REDIRECT_URI": "https://example.test/callback",
        "MOLONI_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }.items():
        monkeypatch.setattr(moloni.settings, name, value, raising=False)
    monkeypatch.setattr(moloni.httpx, "AsyncClient", _Client)

    response = await client.get(
        "/api/v1/integrations/moloni/oauth-return", params={"code": "abc", "state": state}
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(previous)
    assert previous.is_active is False
    assert (await active_moloni_connection(db_session)).company_id == 9102


async def test_enq01_manual_enqueue_validates_order_id_and_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    platform = await make_user(db_session)
    await make_platform_permission(db_session, platform)
    headers = {"Authorization": "Bearer " + create_access_token(
        platform.id, None, platform.auth_version, None, scope="platform"
    )}
    url = "/api/v1/integrations/moloni/orders/{}/enqueue"

    malformed = await client.post(url.format("nao-e-uuid"), headers=headers)
    assert malformed.status_code == 422, malformed.text
    assert malformed.json()["detail"][0]["loc"] == ["path", "order_id"]

    missing = await client.post(url.format(uuid.uuid4()), headers=headers)
    assert missing.status_code == 404, missing.text

    eu_prices = await make_price_list(db_session, market_code="EU")
    eu_order = await make_order(db_session, await make_client(db_session, eu_prices, market_code="EU"), platform.id)
    br_prices = await make_price_list(db_session, market_code="BR")
    br_order = await make_order(db_session, await make_client(db_session, br_prices, market_code="BR"), platform.id)
    br_order.is_finalized, br_order.finalized_at = True, datetime.now(timezone.utc)
    await db_session.flush()

    for order in (eu_order, br_order):
        refused = await client.post(url.format(order.id), headers=headers)
        assert refused.status_code == 422, refused.text

    eu_order.is_finalized, eu_order.finalized_at = True, datetime.now(timezone.utc)
    await db_session.flush()
    queued = await client.post(url.format(eu_order.id), headers=headers)
    assert queued.status_code == 202, queued.text
    jobs = (await db_session.execute(
        select(MoloniExportJob).where(MoloniExportJob.order_id == eu_order.id)
    )).scalars().all()
    assert [job.status for job in jobs] == ["pending"]
