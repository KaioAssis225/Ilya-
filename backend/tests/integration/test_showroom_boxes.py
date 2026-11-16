"""Boxes de showroom EU: RBAC, isolamento, preços vivos e CRUD."""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.market import PriceList, ProductMarket
from app.models.user import UserRole
from tests.factories import (
    make_application,
    make_optional,
    make_optional_category,
    make_product,
    make_product_market,
    make_product_price,
    make_user,
    make_user_market,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
BASE = "/api/v1/showroom-boxes"


def auth(user, role: str, market: str = "EU") -> dict[str, str]:
    token = create_access_token(user.id, role, user.auth_version, market)
    return {"Authorization": f"Bearer {token}"}


async def person(db: AsyncSession, tag: str, *, allowed: bool, role: str = "vendedor"):
    user = await make_user(
        db,
        email=f"showroom-{tag}-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole(role),
        home_market="EU",
    )
    await make_user_market(
        db, user, market_code="EU", role=role,
        can_manage_showrooms=allowed,
    )
    return user


async def eu_price_list(db: AsyncSession, code: str) -> PriceList:
    result = (await db.execute(select(PriceList).where(
        PriceList.market_code == "EU", PriceList.code == code,
    ))).scalar_one()
    return result


async def priced_product(db: AsyncSession):
    product = await make_product(
        db, market_code="EU", description="Cadeira para showroom",
    )
    await make_product_market(db, product)
    await make_product_price(db, product, await eu_price_list(db, "lojista"), amount=Decimal("125.50"))
    await make_product_price(db, product, await eu_price_list(db, "pvp"), amount=Decimal("200.00"))
    return product


async def test_area_e_oculta_sem_permissao_e_no_br(
    client: AsyncClient, db_session: AsyncSession,
):
    allowed = await person(db_session, "allowed", allowed=True)
    plain = await person(db_session, "plain", allowed=False)
    await make_user_market(db_session, allowed, market_code="BR", role="vendedor")
    await db_session.commit()

    assert (await client.get(BASE, headers=auth(plain, "vendedor"))).status_code == 404
    assert (await client.get(BASE, headers=auth(allowed, "vendedor", "BR"))).status_code == 404
    assert (await client.get(BASE, headers=auth(allowed, "vendedor"))).status_code == 200


async def test_admin_eu_tambem_precisa_estar_selecionado(
    client: AsyncClient, db_session: AsyncSession,
):
    admin = await person(db_session, "admin", allowed=False, role="admin")
    await db_session.commit()
    response = await client.get(BASE, headers=auth(admin, "admin"))
    assert response.status_code == 404


async def test_crud_quantidade_e_preco_da_tabela(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await person(db_session, "manager", allowed=True)
    product = await priced_product(db_session)
    await db_session.commit()
    headers = auth(user, "vendedor")

    created = await client.post(BASE, json={
        "name": "Feira Lisboa", "price_list_code": "lojista",
    }, headers=headers)
    assert created.status_code == 201, created.text
    box = created.json()
    assert box["total_value"] == "0.00" and box["items"] == []

    second = await client.post(BASE, json={
        "name": "Showroom Cascais", "price_list_code": "pvp",
    }, headers=headers)
    assert second.status_code == 201
    listed = await client.get(BASE, headers=headers)
    assert {row["name"] for row in listed.json()} >= {"Feira Lisboa", "Showroom Cascais"}

    added = await client.post(f"{BASE}/{box['id']}/items", json={
        "product_id": str(product.id), "quantity": 2,
    }, headers=headers)
    assert added.status_code == 200, added.text
    item = added.json()["items"][0]
    assert item["unit_price"] == "125.50"
    assert item["line_total"] == "251.00"
    assert added.json()["total_quantity"] == 2
    assert added.json()["total_value"] == "251.00"

    quantity = await client.patch(
        f"{BASE}/{box['id']}/items/{item['item_id']}",
        json={"quantity": 3}, headers=headers,
    )
    assert quantity.json()["total_value"] == "376.50"

    repriced = await client.patch(f"{BASE}/{box['id']}", json={
        "name": "Feira Lisboa 2027", "price_list_code": "pvp",
    }, headers=headers)
    assert repriced.status_code == 200, repriced.text
    assert repriced.json()["items"][0]["unit_price"] == "200.00"
    assert repriced.json()["total_value"] == "600.00"

    removed = await client.delete(
        f"{BASE}/{box['id']}/items/{item['item_id']}", headers=headers,
    )
    assert removed.status_code == 200 and removed.json()["items"] == []
    assert (await client.delete(f"{BASE}/{box['id']}", headers=headers)).status_code == 204


async def test_busca_e_adicao_aceitam_somente_produto_eu_com_preco(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await person(db_session, "scope", allowed=True)
    eu = await priced_product(db_session)
    br = await make_product(db_session, market_code="BR", description="Produto Brasil")
    await make_product_market(db_session, br)
    await db_session.commit()
    headers = auth(user, "vendedor")

    box = (await client.post(BASE, json={
        "name": "Escopo EU", "price_list_code": "lojista",
    }, headers=headers)).json()
    search = await client.get(f"{BASE}/products", params={
        "price_list_code": "lojista", "q": eu.product_code,
    }, headers=headers)
    assert [row["id"] for row in search.json()] == [str(eu.id)]

    denied = await client.post(f"{BASE}/{box['id']}/items", json={
        "product_id": str(br.id), "quantity": 1,
    }, headers=headers)
    assert denied.status_code == 422


async def test_mesmo_produto_aceita_configuracoes_distintas_e_localizadas(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await person(db_session, "configured", allowed=True)
    product = await priced_product(db_session)
    product_market = await db_session.get(ProductMarket, (product.id, "EU"))
    assert product_market is not None
    product_market.description_pt_pt = "Cadeira portuguesa"
    product_market.description_en = "Portuguese chair"
    category = await make_optional_category(
        db_session, market_code="EU", code="PINT_SHOWROOM", name="Pintura",
    )
    taupe = await make_optional(db_session, category, color_name="Taupe")
    black = await make_optional(db_session, category, color_name="Preto")
    application = await make_application(
        db_session, product, category,
        name="Pés", name_en="Legs", required=True, allowed=[taupe, black],
    )
    await db_session.commit()
    headers = auth(user, "vendedor")
    box = (await client.post(BASE, json={
        "name": "Configurações", "price_list_code": "lojista",
    }, headers=headers)).json()

    missing = await client.post(f"{BASE}/{box['id']}/items", json={
        "product_id": str(product.id), "quantity": 1,
    }, headers=headers)
    assert missing.status_code == 422

    def payload(optional_id, quantity=1):
        return {
            "product_id": str(product.id), "quantity": quantity,
            "optional_choices": [{
                "application_id": str(application.id),
                "optional_id": str(optional_id),
            }],
        }

    first = await client.post(
        f"{BASE}/{box['id']}/items", json=payload(taupe.id), headers=headers,
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"{BASE}/{box['id']}/items", json=payload(black.id), headers=headers,
    )
    assert second.status_code == 200, second.text
    repeated = await client.post(
        f"{BASE}/{box['id']}/items", json=payload(taupe.id), headers=headers,
        params={"language": "en-GB"},
    )
    assert repeated.status_code == 200, repeated.text
    body = repeated.json()
    assert body["item_count"] == 2
    assert body["total_quantity"] == 3
    assert {row["optional_choices"][0]["optional_name"] for row in body["items"]} == {"Taupe", "Preto"}
    assert {row["description"] for row in body["items"]} == {"Portuguese chair"}
    assert {row["optional_choices"][0]["application_name_en"] for row in body["items"]} == {"Legs"}

    search = await client.get(f"{BASE}/products", params={
        "price_list_code": "lojista", "q": "Portuguese chair", "language": "en-GB",
    }, headers=headers)
    assert search.status_code == 200
    assert search.json()[0]["description"] == "Portuguese chair"
