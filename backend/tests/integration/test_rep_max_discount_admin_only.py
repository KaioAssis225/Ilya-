"""Desconto máximo do representante (teto do PVP no EU): só o admin altera.

Quem não é admin e manda um valor diferente do gravado recebe 403 explícito;
reenviar o mesmo valor (o formulário manda a ficha inteira) segue funcionando.

PostgreSQL real; cada teste roda dentro da transação revertida da fixture.
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from tests.factories import (
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


async def _member(db: AsyncSession, email: str, role: UserRole, market: str, **link) -> User:
    user = await make_user(db, email=email, role=role)
    await make_user_market(db, user, market_code=market, role=role.value, **link)
    return user


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_nao_admin_nao_altera_max_discount_do_representante(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    rep = await make_representative(db_session, market_code=market)
    rep.max_discount = Decimal("30.00")
    await _member(
        db_session, f"md-self-{market}@ilya-test.invalid",
        UserRole.representante, market, rep_id=rep.id,
    )
    await _member(
        db_session, f"md-vend-{market}@ilya-test.invalid", UserRole.vendedor, market,
    )
    await db_session.flush()
    url = f"/api/v1/representatives/{rep.id}"

    for email in (f"md-self-{market}@ilya-test.invalid", f"md-vend-{market}@ilya-test.invalid"):
        headers = await _login(client, email)
        denied = await client.patch(url, json={"max_discount": "50.00"}, headers=headers)
        assert denied.status_code == 403, denied.text
        await db_session.refresh(rep)
        assert rep.max_discount == Decimal("30.00")

        # Reenviar o valor já gravado (ficha inteira) não é alteração.
        same = await client.patch(
            url, json={"max_discount": "30.00", "city": "Cidade Nova"}, headers=headers,
        )
        assert same.status_code == 200, same.text
        assert Decimal(str(same.json()["max_discount"])) == Decimal("30.00")


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_admin_altera_max_discount_do_representante(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    rep = await make_representative(db_session, market_code=market)
    rep.max_discount = Decimal("30.00")
    await _member(
        db_session, f"md-admin-{market}@ilya-test.invalid", UserRole.admin, market,
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/representatives/{rep.id}", json={"max_discount": "50.00"},
        headers=await _login(client, f"md-admin-{market}@ilya-test.invalid"),
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(rep)
    assert rep.max_discount == Decimal("50.00")
