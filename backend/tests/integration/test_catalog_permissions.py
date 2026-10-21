"""Permissões de catálogo por representante e cliente (catalog_permissions_r21).

Cobre as decisões DEC-01..08 do planejamento "Orçamentos, Catálogos e
Permissões Comerciais" v1.2.0 pela API: pedido de um só catálogo, interseção
cliente ∩ representante, quem concede catálogo e visibilidade de produtos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.catalog import Catalog, ClientCatalog, RepresentativeCatalog
from app.models.client import Client
from app.models.market import PriceList
from app.models.product import Product
from app.models.representative import Representative
from app.models.user import UserRole
from tests.factories import (
    make_catalog,
    make_client,
    make_product,
    make_product_group,
    make_product_market,
    make_product_price,
    make_product_type,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _token(
    db: AsyncSession,
    role: UserRole,
    *,
    rep_id: uuid.UUID | None = None,
    linked_client_id: uuid.UUID | None = None,
) -> str:
    user = await make_user(
        db,
        email=f"cat-{role.value}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=role,
    )
    if linked_client_id is not None:
        user.linked_id = linked_client_id
    await make_user_market(
        db, user, market_code="BR", role=role.value,
        rep_id=rep_id, linked_client_id=linked_client_id,
    )
    return create_access_token(user.id, role.value, user.auth_version, "BR")


async def _price_list(db: AsyncSession) -> PriceList:
    return (await db.execute(
        select(PriceList)
        .where(PriceList.market_code == "BR", PriceList.code == "lojista")
        .execution_options(skip_market_scope=True)
    )).scalar_one()


async def _product(db: AsyncSession, catalog: Catalog, price_list: PriceList) -> Product:
    suffix = uuid.uuid4().hex[:8].upper()
    group = await make_product_group(db, market_code="BR", name=f"cat grupo {suffix}")
    product_type = await make_product_type(db, market_code="BR", name=f"cat tipo {suffix}", group=group)
    product = await make_product(db, market_code="BR", catalog=catalog)
    product.type = product_type.name
    await make_product_market(db, product)
    await make_product_price(db, product, price_list, amount=Decimal("100.00"))
    await db.flush()
    return product


async def _restrict(
    db: AsyncSession, owner: Client | Representative, *catalogs: Catalog
) -> None:
    owner.all_catalogs = False
    for catalog in catalogs:
        if isinstance(owner, Client):
            db.add(ClientCatalog(client_id=owner.id, catalog_id=catalog.id, market_code="BR"))
        else:
            db.add(RepresentativeCatalog(representative_id=owner.id, catalog_id=catalog.id, market_code="BR"))
    await db.flush()
    # A rota usa a mesma sessão: recarrega os vínculos no mapa de identidade.
    await db.refresh(owner, ["catalog_links"])


class _Scenario:
    """Dois catálogos com um produto cada, um representante e um cliente dele."""

    async def build(self, db: AsyncSession) -> "_Scenario":
        self.price_list = await _price_list(db)
        self.cat_a = await make_catalog(db, market_code="BR")
        self.cat_b = await make_catalog(db, market_code="BR")
        self.prod_a = await _product(db, self.cat_a, self.price_list)
        self.prod_b = await _product(db, self.cat_b, self.price_list)
        self.rep = await make_representative(db, market_code="BR")
        self.client = await make_client(db, self.price_list, market_code="BR")
        self.client.rep_id = self.rep.id
        await db.flush()
        return self


def _order(client_id: uuid.UUID, *products: Product, rep_id: uuid.UUID | None = None) -> dict:
    payload = {
        "client_id": str(client_id),
        "items": [{"product_code": p.product_code, "qty": 1} for p in products],
    }
    if rep_id is not None:
        payload["rep_id"] = str(rep_id)
    return payload


async def test_pedido_nao_mistura_catalogos_e_guarda_o_catalogo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    admin = await _token(db_session, UserRole.admin)

    mixed = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_a, s.prod_b), headers=_auth(admin))
    assert mixed.status_code == 422, mixed.text

    created = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_a), headers=_auth(admin))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["catalog_id"] == str(s.cat_a.id)
    assert body["catalog_name"] == s.cat_a.name

    # A edição não troca o catálogo do pedido.
    swapped = await client.put(
        f"/api/v1/orders/{body['id']}",
        json={"items": [{"product_code": s.prod_b.product_code, "qty": 1}]},
        headers=_auth(admin),
    )
    assert swapped.status_code == 422, swapped.text

    listed = await client.get("/api/v1/orders?limit=100", headers=_auth(admin))
    row = next(o for o in listed.json() if o["id"] == body["id"])
    assert row["catalog_name"] == s.cat_a.name

    in_use = await client.delete(f"/api/v1/catalogs/{s.cat_a.id}", headers=_auth(admin))
    assert in_use.status_code == 409, in_use.text


async def test_representante_vende_so_a_intersecao_com_o_cliente(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    await _restrict(db_session, s.rep, s.cat_a)
    await db_session.flush()
    rep_token = await _token(db_session, UserRole.representante, rep_id=s.rep.id)

    denied = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_b), headers=_auth(rep_token))
    assert denied.status_code == 403, denied.text
    allowed = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_a), headers=_auth(rep_token))
    assert allowed.status_code == 201, allowed.text

    # Cliente restringido a B: a interseção com o representante (A) fica vazia.
    await _restrict(db_session, s.client, s.cat_b)
    await db_session.flush()
    empty = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_a), headers=_auth(rep_token))
    assert empty.status_code == 403, empty.text


async def test_vendedor_interno_respeita_representante_atribuido(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    await _restrict(db_session, s.rep, s.cat_a)
    await db_session.flush()
    seller = await _token(db_session, UserRole.vendedor)

    # Sem representante, só o cliente conta (cliente em "todos").
    no_rep = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_b), headers=_auth(seller))
    assert no_rep.status_code == 201, no_rep.text

    with_rep = await client.post(
        "/api/v1/orders", json=_order(s.client.id, s.prod_b, rep_id=s.rep.id), headers=_auth(seller),
    )
    assert with_rep.status_code == 403, with_rep.text

    # Atribuir depois o representante restrito também é barrado (DEC-05).
    reassign = await client.put(
        f"/api/v1/orders/{no_rep.json()['id']}", json={"rep_id": str(s.rep.id)}, headers=_auth(seller),
    )
    assert reassign.status_code == 403, reassign.text


async def test_representante_so_concede_catalogos_que_vende(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    await _restrict(db_session, s.rep, s.cat_a)
    await db_session.flush()
    rep_token = await _token(db_session, UserRole.representante, rep_id=s.rep.id)
    base = {
        "name": "Cliente do rep", "phone": "11999999999", "cep": "01000-000",
        "address": "Rua 1", "city": "São Paulo", "state": "SP",
    }

    inherited = await client.post("/api/v1/clients", json=base, headers=_auth(rep_token))
    assert inherited.status_code == 201, inherited.text
    assert inherited.json()["all_catalogs"] is False
    assert inherited.json()["catalog_ids"] == [str(s.cat_a.id)]

    for forbidden in ({"all_catalogs": True}, {"catalog_ids": [str(s.cat_b.id)]}):
        resp = await client.post(
            "/api/v1/clients", json={**base, "name": f"Cliente {uuid.uuid4().hex[:6]}", **forbidden},
            headers=_auth(rep_token),
        )
        assert resp.status_code == 403, resp.text

    # O representante não amplia o próprio cadastro.
    own = await client.patch(
        f"/api/v1/representatives/{s.rep.id}", json={"all_catalogs": True}, headers=_auth(rep_token),
    )
    assert own.status_code == 200, own.text
    assert own.json()["all_catalogs"] is False


async def test_admin_define_catalogos_e_cadastro_novo_nasce_liberado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    admin = await _token(db_session, UserRole.admin)

    current = await client.get(f"/api/v1/clients/{s.client.id}", headers=_auth(admin))
    assert current.json()["all_catalogs"] is True

    restricted = await client.patch(
        f"/api/v1/clients/{s.client.id}", json={"catalog_ids": [str(s.cat_b.id)]}, headers=_auth(admin),
    )
    assert restricted.status_code == 200, restricted.text
    assert restricted.json()["all_catalogs"] is False
    assert restricted.json()["catalog_ids"] == [str(s.cat_b.id)]

    reopened = await client.patch(
        f"/api/v1/clients/{s.client.id}", json={"all_catalogs": True}, headers=_auth(admin),
    )
    assert reopened.json()["all_catalogs"] is True
    assert reopened.json()["catalog_ids"] == []

    empty = await client.patch(
        f"/api/v1/clients/{s.client.id}", json={"all_catalogs": False, "catalog_ids": []}, headers=_auth(admin),
    )
    assert empty.status_code == 422, empty.text


async def test_representante_e_cliente_veem_so_os_proprios_catalogos(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _Scenario().build(db_session)
    await _restrict(db_session, s.rep, s.cat_a)
    await _restrict(db_session, s.client, s.cat_b)
    await db_session.flush()
    rep_token = await _token(db_session, UserRole.representante, rep_id=s.rep.id)
    client_token = await _token(db_session, UserRole.cliente, linked_client_id=s.client.id)
    admin = await _token(db_session, UserRole.admin)

    async def codes(token: str) -> set[str]:
        resp = await client.get("/api/v1/products?limit=1000", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        return {p["product_code"] for p in resp.json()}

    rep_codes = await codes(rep_token)
    assert s.prod_a.product_code in rep_codes and s.prod_b.product_code not in rep_codes
    client_codes = await codes(client_token)
    assert s.prod_b.product_code in client_codes and s.prod_a.product_code not in client_codes
    admin_codes = await codes(admin)
    assert {s.prod_a.product_code, s.prod_b.product_code} <= admin_codes

    hidden = await client.get(f"/api/v1/products/{s.prod_b.id}", headers=_auth(rep_token))
    assert hidden.status_code == 404, hidden.text
    batch = await client.post(
        "/api/v1/products/batch",
        json={"product_codes": [s.prod_a.product_code, s.prod_b.product_code]},
        headers=_auth(rep_token),
    )
    assert [p["product_code"] for p in batch.json()] == [s.prod_a.product_code]

    catalogs = await client.get("/api/v1/catalogs", headers=_auth(rep_token))
    assert {c["id"] for c in catalogs.json()} == {str(s.cat_a.id)}

    # Portal: só o cadastro do cliente vale, o representante não entra (DEC-03).
    portal = await client.post("/api/v1/orders", json=_order(s.client.id, s.prod_b), headers=_auth(client_token))
    assert portal.status_code == 201, portal.text
