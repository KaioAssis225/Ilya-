"""Achados LOW da auditoria Mantis (pass 1).

REP-01   representante não reescreve o próprio tax_id; vendedor não reescreve
         e-mail/CPF/tax_id de representante; admin reescreve e fica trilha.
INV-01   desativar a conta revoga o convite pendente; resgatá-lo não reativa.
SORT-01  conta de cliente não ordena o catálogo pela tabela de preço oculta.
ERASE-01 anonimização self-service cobre os cadastros de todos os mercados.

PostgreSQL real; cada teste roda dentro da transação revertida da fixture.
"""
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_invites import hash_invite_token
from app.core.security import create_access_token
from app.models.client_access_invitation import ClientAccessInvitation
from app.models.privacy_event import PrivacyEvent
from app.models.user import User, UserRole
from tests.factories import (
    make_catalog,
    make_client,
    make_platform_permission,
    make_price_list,
    make_product,
    make_product_market,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PASSWORD = "TestPassword1"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"identifier": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _member(db: AsyncSession, email: str, role: UserRole, **link) -> User:
    user = await make_user(db, email=email, role=role)
    await make_user_market(db, user, market_code="BR", role=role.value, **link)
    return user


async def test_rep01_identity_fields_follow_client_rule(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    rep = await make_representative(db_session, market_code="BR")
    rep.email = "rep.original@ilyamoveis.com.br"
    rep.tax_id = "PT111111111"
    await _member(db_session, "rep01-self@ilya-test.invalid", UserRole.representante, rep_id=rep.id)
    await _member(db_session, "rep01-vend@ilya-test.invalid", UserRole.vendedor)
    admin = await _member(db_session, "rep01-admin@ilya-test.invalid", UserRole.admin)
    await db_session.flush()

    own = await client.patch(
        f"/api/v1/representatives/{rep.id}", json={"tax_id": "PT999999999"},
        headers=await _login(client, "rep01-self@ilya-test.invalid"),
    )
    assert own.status_code == 200, own.text
    other = await client.patch(
        f"/api/v1/representatives/{rep.id}",
        json={"email": "trocado@ilyamoveis.com.br", "cpf_cnpj": "52998224725", "tax_id": "PT888888888"},
        headers=await _login(client, "rep01-vend@ilya-test.invalid"),
    )
    assert other.status_code == 200, other.text
    await db_session.refresh(rep)
    assert (rep.email, rep.cpf_cnpj, rep.tax_id) == ("rep.original@ilyamoveis.com.br", None, "PT111111111")

    by_admin = await client.patch(
        f"/api/v1/representatives/{rep.id}", json={"tax_id": "PT222222222"},
        headers=await _login(client, "rep01-admin@ilya-test.invalid"),
    )
    assert by_admin.status_code == 200, by_admin.text
    await db_session.refresh(rep)
    assert rep.tax_id == "PT222222222"
    events = (await db_session.execute(select(PrivacyEvent).where(
        PrivacyEvent.subject_id == rep.id, PrivacyEvent.action == "identity_updated",
    ))).scalars().all()
    assert len(events) == 1
    assert events[0].actor_user_id == admin.id
    assert events[0].context["fields"] == ["tax_id"]


async def test_inv01_deactivation_revokes_pending_invitation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    prices = await make_price_list(db_session, market_code="BR")
    own = await make_client(db_session, prices, market_code="BR")
    own.email = "inv01-cliente@ilya-test.invalid"
    invited = await _member(
        db_session, "inv01-cliente@ilya-test.invalid", UserRole.cliente, linked_client_id=own.id
    )
    invited.is_active = False
    invited.linked_id = own.id  # o fluxo de convite grava o vínculo legado
    invited.must_change_password = True
    platform = await make_user(db_session, email="inv01-platform@ilya-test.invalid")
    await make_platform_permission(db_session, platform)
    token = secrets.token_urlsafe(40)
    now = datetime.now(timezone.utc)
    db_session.add(ClientAccessInvitation(
        user_id=invited.id, client_id=own.id, market_code="BR",
        token_hash=hash_invite_token(token), recipient_email=own.email,
        issued_by_user_id=platform.id, verified_by_user_id=platform.id,
        verification_method="in_person", verified_at=now,
        expires_at=now + timedelta(minutes=30), sent_at=now,
    ))
    await db_session.flush()
    platform_token = create_access_token(platform.id, None, platform.auth_version, None, scope="platform")

    deactivate = await client.patch(
        f"/api/v1/users/{invited.id}", json={"is_active": False},
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert deactivate.status_code == 200, deactivate.text
    redeem = await client.post(
        "/api/v1/auth/activate-client", json={"token": token, "new_password": "NovaSenhaForte9"}
    )

    assert redeem.status_code == 400, redeem.text
    await db_session.refresh(invited)
    assert invited.is_active is False


async def test_sort01_client_cannot_sort_by_hidden_price_table(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    catalog = await make_catalog(db_session, market_code="BR", name="SORT01")
    prefix = f"SRT{secrets.token_hex(3).upper()}"
    for suffix, corporativo in (("A", "300"), ("B", "100"), ("C", "200")):
        product = await make_product(
            db_session, market_code="BR", product_code=f"{prefix}-{suffix}", catalog=catalog
        )
        product.price_corporativo = Decimal(corporativo)
        await make_product_market(db_session, product)
    prices = await make_price_list(db_session, market_code="BR")
    own = await make_client(db_session, prices, market_code="BR")
    await _member(db_session, "sort01-cliente@ilya-test.invalid", UserRole.cliente, linked_client_id=own.id)
    await _member(db_session, "sort01-admin@ilya-test.invalid", UserRole.admin)
    await db_session.flush()
    params = {"q": prefix, "sort_by": "price_corporativo", "limit": 10}

    async def codes(email: str) -> list[str]:
        response = await client.get(
            "/api/v1/products", params=params, headers=await _login(client, email)
        )
        assert response.status_code == 200, response.text
        return [item["product_code"] for item in response.json()]

    assert await codes("sort01-admin@ilya-test.invalid") == [f"{prefix}-B", f"{prefix}-C", f"{prefix}-A"]
    assert await codes("sort01-cliente@ilya-test.invalid") == [f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"]


async def test_erase01_self_service_erasure_covers_every_market(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    br = await make_client(db_session, await make_price_list(db_session, market_code="BR"), market_code="BR", name="Titular BR")
    eu = await make_client(db_session, await make_price_list(db_session, market_code="EU"), market_code="EU", name="Titular EU")
    eu.tax_id = "PT123456789"
    user = await make_user(db_session, email="erase01@ilya-test.invalid", role=UserRole.cliente)
    await make_user_market(db_session, user, market_code="BR", role="cliente", linked_client_id=br.id)
    await make_user_market(db_session, user, market_code="EU", role="cliente", linked_client_id=eu.id)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/anonymize", json={"password": _PASSWORD},
        headers=await _login(client, "erase01@ilya-test.invalid"),
    )

    assert response.status_code == 204, response.text
    await db_session.refresh(br)
    await db_session.refresh(eu)
    assert br.name == eu.name == "CLIENTE ANONIMIZADO"
    assert eu.tax_id is None
    subjects = set((await db_session.execute(select(PrivacyEvent.subject_id).where(
        PrivacyEvent.action == "personal_data_anonymized",
        PrivacyEvent.subject_id.in_([br.id, eu.id]),
    ))).scalars())
    assert subjects == {br.id, eu.id}


async def test_inv02_valid_invitation_activates_with_204(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """activate-client tem rate limit com headers; sem `response` o slowapi
    derrubava a resposta com 500 depois do commit da ativação."""
    prices = await make_price_list(db_session, market_code="BR")
    own = await make_client(db_session, prices, market_code="BR")
    own.email = "inv02-cliente@ilyamoveis.com.br"
    invited = await _member(
        db_session, "inv02-cliente@ilyamoveis.com.br", UserRole.cliente, linked_client_id=own.id
    )
    invited.is_active = False
    invited.must_change_password = True
    invited.linked_id = own.id
    issuer = await make_user(db_session, email="inv02-platform@ilya-test.invalid")
    token = secrets.token_urlsafe(40)
    now = datetime.now(timezone.utc)
    db_session.add(ClientAccessInvitation(
        user_id=invited.id, client_id=own.id, market_code="BR",
        token_hash=hash_invite_token(token), recipient_email=own.email,
        issued_by_user_id=issuer.id, verified_by_user_id=issuer.id,
        verification_method="in_person", verified_at=now,
        expires_at=now + timedelta(minutes=30), sent_at=now,
    ))
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/activate-client", json={"token": token, "new_password": "NovaSenhaForte9"}
    )

    assert response.status_code == 204, response.text
    await db_session.refresh(invited)
    assert invited.is_active is True
