"""Controles LGPD sobre exclusão, anonimização e acesso do titular.

HOLD-01..04  retenção legal ativa bloqueia exclusão e anonimização (409) e
             nada é alterado no cadastro.
DEL-01       exclusão física de cliente registra evento de privacidade.
ANON-01      anonimização remove identificação fiscal e região.
ACCESS-01    /auth/my-data exporta vínculos de todos os mercados com os campos
             fiscais e de localização.

PostgreSQL real; cada teste roda dentro da transação revertida da fixture.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.privacy_event import PrivacyEvent
from app.models.retention import LegalHold
from app.models.user import UserRole
from tests.factories import (
    make_client,
    make_price_list,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PASSWORD = "TestPassword1"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": _PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _admin(db: AsyncSession, email: str):
    user = await make_user(db, email=email, role=UserRole.admin)
    await make_user_market(db, user, market_code="BR", role="admin")
    return user


async def _hold(db: AsyncSession, subject_type: str, subject_id) -> LegalHold:
    hold = LegalHold(
        subject_type=subject_type,
        subject_id=subject_id,
        reason="Processo judicial em andamento (teste)",
    )
    db.add(hold)
    await db.flush()
    return hold


async def test_hold01_rep_cannot_delete_client_under_legal_hold(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    rep = await make_representative(db_session, market_code="BR")
    price_list = await make_price_list(db_session, market_code="BR")
    target = await make_client(db_session, price_list, market_code="BR", name="Cliente Retido")
    target.rep_id = rep.id
    user = await make_user(db_session, email="hold01@ilya-test.invalid", role=UserRole.representante)
    await make_user_market(db_session, user, market_code="BR", role="representante", rep_id=rep.id)
    await _hold(db_session, "client", target.id)

    headers = await _login(client, "hold01@ilya-test.invalid")
    response = await client.delete(f"/api/v1/clients/{target.id}", headers=headers)

    assert response.status_code == 409, response.text
    assert await db_session.get(Client, target.id) is not None


async def test_hold02_admin_cannot_anonymize_client_under_legal_hold(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    price_list = await make_price_list(db_session, market_code="BR")
    target = await make_client(db_session, price_list, market_code="BR", name="Cliente Retido")
    await _admin(db_session, "hold02@ilya-test.invalid")
    await _hold(db_session, "client", target.id)

    headers = await _login(client, "hold02@ilya-test.invalid")
    response = await client.post(f"/api/v1/clients/{target.id}/anonymize", headers=headers)

    assert response.status_code == 409, response.text
    await db_session.refresh(target)
    assert target.name == "Cliente Retido"


async def test_hold03_admin_cannot_anonymize_representative_under_legal_hold(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    rep = await make_representative(db_session, market_code="BR", name="Rep Retido")
    await _admin(db_session, "hold03@ilya-test.invalid")
    await _hold(db_session, "representative", rep.id)

    headers = await _login(client, "hold03@ilya-test.invalid")
    response = await client.post(f"/api/v1/representatives/{rep.id}/anonymize", headers=headers)

    assert response.status_code == 409, response.text
    await db_session.refresh(rep)
    assert rep.name == "Rep Retido"


async def test_hold04_self_service_anonymization_blocked_under_legal_hold(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    price_list = await make_price_list(db_session, market_code="BR")
    own = await make_client(db_session, price_list, market_code="BR", name="Titular Retido")
    user = await make_user(db_session, email="hold04@ilya-test.invalid", role=UserRole.cliente)
    await make_user_market(db_session, user, market_code="BR", role="cliente", linked_client_id=own.id)
    await _hold(db_session, "client", own.id)

    headers = await _login(client, "hold04@ilya-test.invalid")
    response = await client.post(
        "/api/v1/auth/anonymize", json={"password": _PASSWORD}, headers=headers
    )

    assert response.status_code == 409, response.text
    await db_session.refresh(own)
    await db_session.refresh(user)
    assert own.name == "Titular Retido"
    assert user.is_active is True


async def test_del01_client_deletion_records_privacy_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    price_list = await make_price_list(db_session, market_code="BR")
    target = await make_client(db_session, price_list, market_code="BR")
    admin = await _admin(db_session, "del01@ilya-test.invalid")
    target_id = target.id

    headers = await _login(client, "del01@ilya-test.invalid")
    response = await client.delete(f"/api/v1/clients/{target_id}", headers=headers)

    assert response.status_code == 204, response.text
    events = (await db_session.execute(
        select(PrivacyEvent).where(
            PrivacyEvent.subject_id == target_id,
            PrivacyEvent.action == "personal_data_deleted",
        )
    )).scalars().all()
    assert len(events) == 1
    assert events[0].actor_user_id == admin.id
    assert events[0].subject_type == "client"


async def test_anon01_admin_anonymization_clears_tax_id_and_region(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    price_list = await make_price_list(db_session, market_code="BR")
    target = await make_client(db_session, price_list, market_code="BR")
    target.tax_id = "PT123456789"
    target.region = "Lisboa"
    rep = await make_representative(db_session, market_code="BR")
    rep.tax_id = "PT987654321"
    rep.region = "Porto"
    await _admin(db_session, "anon01@ilya-test.invalid")
    await db_session.flush()

    headers = await _login(client, "anon01@ilya-test.invalid")
    assert (await client.post(f"/api/v1/clients/{target.id}/anonymize", headers=headers)).status_code == 204
    assert (await client.post(f"/api/v1/representatives/{rep.id}/anonymize", headers=headers)).status_code == 204

    await db_session.refresh(target)
    await db_session.refresh(rep)
    assert (target.tax_id, target.region) == (None, None)
    assert (rep.tax_id, rep.region) == (None, None)


async def test_access01_my_data_exports_every_market_link_with_fiscal_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    br_prices = await make_price_list(db_session, market_code="BR")
    eu_prices = await make_price_list(db_session, market_code="EU")
    br_client = await make_client(db_session, br_prices, market_code="BR", name="Titular BR")
    eu_client = await make_client(db_session, eu_prices, market_code="EU", name="Titular EU")
    eu_client.tax_id = "PT123456789"
    eu_client.region = "Lisboa"
    user = await make_user(db_session, email="access01@ilya-test.invalid", role=UserRole.cliente)
    await make_user_market(db_session, user, market_code="BR", role="cliente", linked_client_id=br_client.id)
    await make_user_market(db_session, user, market_code="EU", role="cliente", linked_client_id=eu_client.id)
    await db_session.flush()

    headers = await _login(client, "access01@ilya-test.invalid")
    response = await client.get("/api/v1/auth/my-data", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    by_market = {link["mercado"]: link for link in body["vinculos_por_mercado"]}
    assert set(by_market) == {"BR", "EU"}
    assert by_market["BR"]["cliente"]["nome"] == "Titular BR"
    eu = by_market["EU"]["cliente"]
    assert eu["nome"] == "Titular EU"
    assert eu["identificacao_fiscal"] == "PT123456789"
    assert eu["regiao"] == "Lisboa"
    assert eu["pais"] == eu_client.country
    assert body["dados_cliente"]["nome"] == "Titular BR"
    assert "identificacao_fiscal" in body["dados_cliente"]
