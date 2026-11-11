"""Protótipos (EU): permissão, dono, código PROT, exclusão das listas comuns.

PostgreSQL real. Dados 100% sintéticos. Cobre o PR A: banco (CHECKs e sequência),
RBAC (sem permissão = 404 em tudo), ownership (só o criador enxerga), sequência
`PROT-xxxx` atômica, negação por padrão no ORM e administração da permissão.
"""
import asyncio
import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token
from app.models.market import PriceList, UserMarket
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import (
    make_catalog,
    make_platform_permission,
    make_product,
    make_product_group,
    make_product_market,
    make_product_type,
    make_user,
    make_user_market,
)
from tests.integration.conftest import _resolve_db_url

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PROTOTYPES = "/api/v1/prototypes"
_SKIP = {"skip_market_scope": True}


@pytest.fixture(autouse=True)
def disco(tmp_path, monkeypatch):
    raiz = tmp_path / "uploads"
    raiz.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(raiz))
    return raiz


def _auth(user, role: str, market: str = "EU") -> dict[str, str]:
    token = create_access_token(user.id, role, user.auth_version, market)
    return {"Authorization": f"Bearer {token}"}


async def _person(
    db: AsyncSession, tag: str, *, role: str = "vendedor", prototypes: bool = False,
    markets: tuple[str, ...] = ("EU",),
):
    user = await make_user(
        db, email=f"pr-{tag}-{uuid.uuid4().hex[:6]}@ilya-test.invalid",
        role=UserRole(role), home_market=markets[0],
    )
    for market in markets:
        await make_user_market(
            db, user, market_code=market, role=role,
            can_manage_prototypes=prototypes and market == "EU",
        )
    return user


class World:
    def __init__(self, catalog, product_type, james, other, plain, admin):
        self.catalog = catalog
        self.type = product_type
        self.james = james
        self.other = other
        self.plain = plain
        self.admin = admin

    def body(self, **extra) -> dict:
        return {
            "description_pt_pt": "Poltrona protótipo",
            "description_en": "Prototype armchair",
            "type": self.type.name,
            "catalog_id": str(self.catalog.id),
            "altura": "0.80", "largura": "0.70", "profundidade": "0.75",
            "price_lojista": "1000.00", "price_corporativo": "900.00",
            "price_pvp": "1500.00", "price_arquiteto": "1100.00",
            "vat_rate": "23.00",
            **extra,
        }


async def _world(db: AsyncSession) -> World:
    catalog = await make_catalog(db, market_code="EU")
    group = await make_product_group(db, market_code="EU")
    product_type = await make_product_type(db, market_code="EU", group=group)
    james = await _person(db, "james", prototypes=True)
    other = await _person(db, "other", prototypes=True)
    plain = await _person(db, "plain")
    admin = await _person(db, "admin", role="admin")
    await db.commit()
    return World(catalog, product_type, james, other, plain, admin)


async def _create(client: AsyncClient, w: World, who=None, **extra) -> dict:
    who = who or w.james
    response = await client.post(PROTOTYPES, json=w.body(**extra), headers=_auth(who, "vendedor"))
    assert response.status_code == 201, response.text
    return response.json()


def _png() -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 90, 160)).save(saida, format="PNG")
    return saida.getvalue()


def _number(code: str) -> int:
    assert code.startswith("PROT-")
    return int(code.removeprefix("PROT-"))


# ── RBAC: quem não tem a permissão não vê nada ────────────────────────────────

async def test_sem_permissao_tudo_responde_404(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    mine = await _create(client, w)
    fake = uuid.uuid4()
    for who, role in ((w.plain, "vendedor"), (w.admin, "admin")):
        headers = _auth(who, role)
        assert (await client.post(PROTOTYPES, json=w.body(), headers=headers)).status_code == 404
        assert (await client.get(PROTOTYPES, headers=headers)).status_code == 404
        assert (await client.get(f"{PROTOTYPES}/{mine['id']}", headers=headers)).status_code == 404
        assert (await client.get(f"{PROTOTYPES}/{fake}", headers=headers)).status_code == 404
        assert (await client.patch(f"{PROTOTYPES}/{mine['id']}", json={"observacao": "x"}, headers=headers)).status_code == 404
        assert (await client.delete(f"{PROTOTYPES}/{mine['id']}", headers=headers)).status_code == 404
        photo = await client.post(
            f"{PROTOTYPES}/{mine['id']}/photos",
            files={"file": ("foto.png", _png(), "image/png")}, headers=headers,
        )
        assert photo.status_code == 404


async def test_sem_login_e_401_e_404_igual_a_rota_inexistente(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    assert (await client.get(PROTOTYPES)).status_code == 401
    hidden = await client.get(PROTOTYPES, headers=_auth(w.plain, "vendedor"))
    missing = await client.get("/api/v1/rota-que-nao-existe", headers=_auth(w.plain, "vendedor"))
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()


async def test_permissao_so_vale_no_mercado_eu(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    both = await _person(db_session, "both", prototypes=True, markets=("EU", "BR"))
    await db_session.commit()
    assert (await client.get(PROTOTYPES, headers=_auth(both, "vendedor", "EU"))).status_code == 200
    assert (await client.get(PROTOTYPES, headers=_auth(both, "vendedor", "BR"))).status_code == 404
    assert (await client.post(PROTOTYPES, json=w.body(), headers=_auth(both, "vendedor", "BR"))).status_code == 404


async def test_papel_nao_permitido_nao_acessa_mesmo_com_a_flag(client: AsyncClient, db_session: AsyncSession):
    cadastros = await _person(db_session, "cad", role="cadastros", prototypes=True)
    await db_session.commit()
    response = await client.get(PROTOTYPES, headers=_auth(cadastros, "cadastros"))
    assert response.status_code == 404


async def test_perder_a_permissao_fecha_o_acesso_na_hora(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    mine = await _create(client, w)
    link = await db_session.get(UserMarket, (w.james.id, "EU"))
    link.can_manage_prototypes = False
    await db_session.commit()
    headers = _auth(w.james, "vendedor")
    assert (await client.get(PROTOTYPES, headers=headers)).status_code == 404
    assert (await client.get(f"{PROTOTYPES}/{mine['id']}", headers=headers)).status_code == 404


async def test_vinculo_suspenso_nao_acessa(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    link = await db_session.get(UserMarket, (w.james.id, "EU"))
    link.status = "suspended"
    await db_session.commit()
    assert (await client.get(PROTOTYPES, headers=_auth(w.james, "vendedor"))).status_code == 401


# ── Criação, código PROT e dono ───────────────────────────────────────────────

async def test_criar_gera_codigo_prot_sequencial_e_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    first = await _create(client, w)
    second = await _create(client, w, description_pt_pt="Segundo protótipo")
    assert first["product_code"].startswith("PROT-") and len(first["product_code"]) >= 9
    assert _number(second["product_code"]) == _number(first["product_code"]) + 1
    assert first["is_prototype"] is True
    assert first["market_code"] == "EU" and first["currency"] == "EUR"
    assert first["vat_rate"] == "23.00"
    assert first["market_prices"] == {
        "lojista": "1000.00", "corporativo": "900.00", "pvp": "1500.00", "arquiteto": "1100.00",
    }
    assert first["description_pt_pt"] == "Poltrona protótipo"
    assert first["description_en"] == "Prototype armchair"
    row = (await db_session.execute(
        select(Product).where(Product.id == uuid.UUID(first["id"])).execution_options(include_prototypes=True)
    )).scalar_one()
    assert row.created_by_user_id == w.james.id and row.is_prototype and row.is_active


async def test_corpo_nao_aceita_codigo_nem_campos_de_sistema(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    for extra in ({"product_code": "PROT-0001"}, {"is_prototype": False}, {"created_by_user_id": str(w.other.id)}):
        response = await client.post(PROTOTYPES, json=w.body(**extra), headers=_auth(w.james, "vendedor"))
        assert response.status_code == 422, extra


async def test_criar_valida_catalogo_e_tipo_do_mercado(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    br_catalog = await make_catalog(db_session, market_code="BR")
    await db_session.commit()
    headers = _auth(w.james, "vendedor")
    assert (await client.post(PROTOTYPES, json=w.body(catalog_id=str(br_catalog.id)), headers=headers)).status_code == 422
    assert (await client.post(PROTOTYPES, json=w.body(type="Tipo inexistente"), headers=headers)).status_code == 422


async def test_sequencia_prot_e_atomica_entre_conexoes(db_session: AsyncSession):
    """10 conexões simultâneas pedem número ao mesmo tempo: nenhum repete."""
    engine = create_async_engine(_resolve_db_url(), poolclass=NullPool)

    async def take() -> int:
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT nextval('prototype_code_seq')"))).scalar_one()

    try:
        numbers = await asyncio.gather(*(take() for _ in range(10)))
    finally:
        await engine.dispose()
    assert len(set(numbers)) == 10


async def test_dono_e_o_unico_que_enxerga(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    mine = await _create(client, w)
    theirs = await _create(client, w, who=w.other, description_pt_pt="Do outro")
    other_headers = _auth(w.other, "vendedor")
    assert (await client.get(f"{PROTOTYPES}/{mine['id']}", headers=other_headers)).status_code == 404
    assert (await client.patch(f"{PROTOTYPES}/{mine['id']}", json={"observacao": "x"}, headers=other_headers)).status_code == 404
    assert (await client.delete(f"{PROTOTYPES}/{mine['id']}", headers=other_headers)).status_code == 404
    photo = await client.post(
        f"{PROTOTYPES}/{mine['id']}/photos", files={"file": ("f.png", _png(), "image/png")}, headers=other_headers,
    )
    assert photo.status_code == 404
    listed = await client.get(PROTOTYPES, headers=other_headers)
    assert [row["id"] for row in listed.json()] == [theirs["id"]]
    listed_james = await client.get(PROTOTYPES, headers=_auth(w.james, "vendedor"))
    assert [row["id"] for row in listed_james.json()] == [mine["id"]]
    # O dono continua com tudo intacto.
    assert (await client.get(f"{PROTOTYPES}/{mine['id']}", headers=_auth(w.james, "vendedor"))).status_code == 200


async def test_listar_busca_ordena_e_pagina(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    a = await _create(client, w, description_pt_pt="Poltrona azul", description_en="Blue armchair")
    b = await _create(client, w, description_pt_pt="Mesa redonda", description_en="Round table")
    headers = _auth(w.james, "vendedor")
    all_rows = await client.get(PROTOTYPES, headers=headers)
    assert [r["id"] for r in all_rows.json()] == [b["id"], a["id"]]  # mais novo primeiro
    assert all_rows.headers["X-Total-Count"] == "2"
    found = await client.get(PROTOTYPES, params={"q": "azul"}, headers=headers)
    assert [r["id"] for r in found.json()] == [a["id"]]
    found_en = await client.get(PROTOTYPES, params={"q": "round"}, headers=headers)
    assert [r["id"] for r in found_en.json()] == [b["id"]]
    by_code = await client.get(PROTOTYPES, params={"q": a["product_code"]}, headers=headers)
    assert [r["id"] for r in by_code.json()] == [a["id"]]
    page = await client.get(PROTOTYPES, params={"limit": 1, "sort_dir": "asc"}, headers=headers)
    assert [r["id"] for r in page.json()] == [a["id"]]
    assert page.headers["X-Has-More"] == "true"


async def test_editar_preco_iva_e_nomes(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    created = await _create(client, w)
    headers = _auth(w.james, "vendedor")
    only_vat = await client.patch(f"{PROTOTYPES}/{created['id']}", json={"vat_rate": "6.00"}, headers=headers)
    assert only_vat.status_code == 200, only_vat.text
    assert only_vat.json()["vat_rate"] == "6.00"
    changed = await client.patch(
        f"{PROTOTYPES}/{created['id']}",
        json={"price_pvp": "1700.00", "description_pt_pt": "Poltrona v2", "largura": "0.72"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["market_prices"]["pvp"] == "1700.00"
    assert body["description_pt_pt"] == "Poltrona v2" and body["description"] == "Poltrona v2"
    assert body["largura"] == "0.72"
    assert body["vat_rate"] == "6.00"
    assert body["product_code"] == created["product_code"] and body["is_prototype"] is True
    for bad in ({"vat_rate": "101"}, {"vat_rate": None}, {"catalog_id": None}, {"product_code": "X"}, {}):
        assert (await client.patch(f"{PROTOTYPES}/{created['id']}", json=bad, headers=headers)).status_code == 422, bad


async def test_excluir_desativa_e_o_codigo_nao_volta(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    first = await _create(client, w)
    headers = _auth(w.james, "vendedor")
    assert (await client.delete(f"{PROTOTYPES}/{first['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"{PROTOTYPES}/{first['id']}", headers=headers)).status_code == 404
    assert (await client.get(PROTOTYPES, headers=headers)).json() == []
    second = await _create(client, w)
    assert _number(second["product_code"]) > _number(first["product_code"])
    row = (await db_session.execute(
        select(Product).where(Product.id == uuid.UUID(first["id"])).execution_options(include_prototypes=True)
    )).scalar_one()
    assert row.is_active is False


async def test_fotos_do_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    created = await _create(client, w)
    headers = _auth(w.james, "vendedor")
    url = f"{PROTOTYPES}/{created['id']}/photos"
    first = await client.post(url, files={"file": ("a.png", _png(), "image/png")}, headers=headers)
    assert first.status_code == 201, first.text
    second = await client.post(url, files={"file": ("b.png", _png(), "image/png")}, headers=headers)
    assert second.status_code == 201, second.text
    photos = second.json()["photos"]
    assert len(photos) == 2 and sum(p["is_primary"] for p in photos) == 1
    other_id = next(p["id"] for p in photos if not p["is_primary"])
    primary = await client.put(f"{url}/{other_id}/primary", headers=headers)
    assert primary.status_code == 200 and primary.json()["photo_count"] == 2
    order = await client.put(f"{url}/order", json={"photo_ids": [p["id"] for p in reversed(photos)]}, headers=headers)
    assert order.status_code == 200
    removed = await client.delete(f"{url}/{other_id}", headers=headers)
    assert removed.status_code == 200 and removed.json()["photo_count"] == 1
    # Fotos de protótipo alheio nunca são tocadas por outro usuário.
    foreign = _auth(w.other, "vendedor")
    only = removed.json()["photos"][0]["id"]
    assert (await client.delete(f"{url}/{only}", headers=foreign)).status_code == 404
    assert (await client.put(f"{url}/{only}/primary", headers=foreign)).status_code == 404


# ── Exclusão das listas comuns (negação por padrão) ───────────────────────────

async def test_prototipo_nao_aparece_no_catalogo_nem_para_o_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    created = await _create(client, w)
    normal = await make_product(db_session, market_code="EU", catalog=w.catalog, description="Produto comum")
    await make_product_market(db_session, normal)
    await db_session.commit()
    for who, role in ((w.james, "vendedor"), (w.plain, "vendedor"), (w.admin, "admin")):
        headers = _auth(who, role)
        listing = await client.get("/api/v1/products", params={"q": "PROT"}, headers=headers)
        assert listing.status_code == 200 and listing.json() == []
        everything = await client.get("/api/v1/products", params={"limit": 1000}, headers=headers)
        codes = {row["product_code"] for row in everything.json()}
        assert created["product_code"] not in codes and normal.product_code in codes
        assert (await client.get(f"/api/v1/products/{created['id']}", headers=headers)).status_code == 404
        batch = await client.post(
            "/api/v1/products/batch", json={"product_codes": [created["product_code"]]}, headers=headers,
        )
        # O dono vê o PRÓPRIO protótipo no /batch (montar orçamento); os demais, nada.
        assert batch.status_code == 200 and (batch.json() == [] or who is w.james)
        options = await client.get("/api/v1/products/filter-options", headers=headers)
        assert options.status_code == 200
        assert (await client.patch(
            f"/api/v1/products/{created['id']}", json={"observacao": "x"}, headers=headers,
        )).status_code == 404
        assert (await client.delete(f"/api/v1/products/{created['id']}", headers=headers)).status_code in (403, 404)


async def test_orm_nega_por_padrao_e_so_abre_para_o_dono(db_session: AsyncSession, client: AsyncClient):
    w = await _world(db_session)
    created = await _create(client, w)
    pid = uuid.UUID(created["id"])
    stmt = select(Product.id).where(Product.id == pid)
    assert (await db_session.execute(stmt)).scalar_one_or_none() is None
    assert (await db_session.execute(stmt.execution_options(**_SKIP))).scalar_one_or_none() is None
    assert (await db_session.execute(stmt.execution_options(include_prototypes=False))).scalar_one_or_none() is None
    assert (await db_session.execute(stmt.execution_options(include_prototypes=w.other.id))).scalar_one_or_none() is None
    assert (await db_session.execute(stmt.execution_options(include_prototypes=w.james.id))).scalar_one_or_none() == pid
    assert (await db_session.execute(stmt.execution_options(include_prototypes=True))).scalar_one_or_none() == pid
    # Joins também passam pelo filtro.
    joined = (await db_session.execute(
        select(Product.id).join(PriceList, PriceList.market_code == Product.market_code).where(Product.id == pid)
    )).first()
    assert joined is None


async def test_produto_normal_nao_pode_usar_o_prefixo_prot(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    producer = await _person(db_session, "prod", role="produtos")
    await db_session.commit()
    headers = _auth(producer, "produtos")
    lists = {p.code for p in (await db_session.execute(
        select(PriceList).where(PriceList.market_code == "EU").execution_options(**_SKIP)
    )).scalars()}
    assert {"lojista", "corporativo", "pvp", "arquiteto"} <= lists
    body = {
        "product_code": "prot-9999", "description": "Tentativa", "type": w.type.name,
        "catalog_id": str(w.catalog.id), "altura": "1.00", "largura": "1.00", "profundidade": "1.00",
        "description_pt_pt": "Tentativa", "description_en": "Attempt",
        "price_lojista": "10.00", "price_corporativo": "10.00", "price_pvp": "10.00", "price_arquiteto": "10.00",
    }
    refused = await client.post("/api/v1/products", json=body, headers=headers)
    assert refused.status_code == 422, refused.text
    ok = await client.post("/api/v1/products", json={**body, "product_code": "COMUM-1"}, headers=headers)
    assert ok.status_code == 201, ok.text
    rename = await client.patch(f"/api/v1/products/{ok.json()['id']}", json={"product_code": "PROT-0005"}, headers=headers)
    assert rename.status_code == 422, rename.text


# ── Banco: constraints ────────────────────────────────────────────────────────

async def test_constraints_do_banco(db_session: AsyncSession):
    w = await _world(db_session)
    catalog_eu = w.catalog
    catalog_br = await make_catalog(db_session, market_code="BR")

    def proto(**over) -> Product:
        base = dict(
            market_code="EU", product_code=f"PROT-{uuid.uuid4().int % 90000 + 10000}",
            description="x", type="Outro", catalog_id=catalog_eu.id,
            altura=1, largura=1, profundidade=1, is_prototype=True, created_by_user_id=w.james.id,
        )
        return Product(**{**base, **over})

    for bad in (
        proto(market_code="BR", catalog_id=catalog_br.id),   # protótipo só em EU
        proto(created_by_user_id=None),                       # sempre com dono
        proto(product_code="COMUM-77"),                       # prefixo reservado
    ):
        async with db_session.begin_nested():
            db_session.add(bad)
            with pytest.raises(IntegrityError):
                await db_session.flush()
    async with db_session.begin_nested():
        good = proto()
        db_session.add(good)
        await db_session.flush()
    assert good.id is not None

    async with db_session.begin_nested():
        bad_link = UserMarket(user_id=w.plain.id, market_code="BR", role="vendedor", status="active",
                              can_manage_prototypes=True)
        db_session.add(bad_link)
        with pytest.raises(IntegrityError):
            await db_session.flush()


# ── Administração da permissão e /auth/me ─────────────────────────────────────

async def _platform_headers(db: AsyncSession) -> dict[str, str]:
    platform = await make_user(db, email=f"pr-plat-{uuid.uuid4().hex[:6]}@ilya-test.invalid", role=UserRole.admin)
    await make_platform_permission(db, platform, capability="platform_admin")
    await db.commit()
    token = create_access_token(platform.id, None, platform.auth_version, None, scope="platform")
    return {"Authorization": f"Bearer {token}"}


def _new_user(email: str, **access) -> dict:
    return {
        "email": email, "password": "SenhaForte123", "full_name": "Pessoa", "role": "vendedor",
        "home_market": access.get("market_code", "EU"),
        "market_accesses": [{"role": "vendedor", "status": "active", **access}],
    }


async def test_admin_liga_a_permissao_so_no_eu(client: AsyncClient, db_session: AsyncSession):
    headers = await _platform_headers(db_session)
    created = await client.post(
        "/api/v1/users",
        json=_new_user("pr-ok@example.com", market_code="EU", can_manage_prototypes=True),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["market_accesses"][0]["can_manage_prototypes"] is True

    in_br = await client.post(
        "/api/v1/users",
        json=_new_user("pr-br@example.com", market_code="BR", can_manage_prototypes=True),
        headers=headers,
    )
    assert in_br.status_code == 422, in_br.text
    wrong_role = _new_user("pr-cli@example.com", market_code="EU", can_manage_prototypes=True)
    wrong_role["market_accesses"][0]["role"] = "cadastros"
    assert (await client.post("/api/v1/users", json=wrong_role, headers=headers)).status_code == 422

    default_off = await client.post(
        "/api/v1/users", json=_new_user("pr-off@example.com", market_code="EU"), headers=headers,
    )
    assert default_off.status_code == 201
    assert default_off.json()["market_accesses"][0]["can_manage_prototypes"] is False


async def test_admin_edita_e_retira_a_permissao(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    headers = await _platform_headers(db_session)
    patch = await client.patch(
        f"/api/v1/users/{w.plain.id}",
        json={"market_accesses": [{
            "market_code": "EU", "role": "vendedor", "status": "active", "can_manage_prototypes": True,
        }]},
        headers=headers,
    )
    assert patch.status_code == 200, patch.text
    await db_session.refresh(w.plain)
    token_headers = _auth(w.plain, "vendedor")
    assert (await client.get(PROTOTYPES, headers=token_headers)).status_code == 200
    off = await client.patch(
        f"/api/v1/users/{w.plain.id}",
        json={"market_accesses": [{
            "market_code": "EU", "role": "vendedor", "status": "active", "can_manage_prototypes": False,
        }]},
        headers=headers,
    )
    assert off.status_code == 200, off.text
    await db_session.refresh(w.plain)
    assert (await client.get(PROTOTYPES, headers=_auth(w.plain, "vendedor"))).status_code == 404


async def test_auth_me_expoe_a_permissao_do_mercado_ativo(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    both = await _person(db_session, "me", prototypes=True, markets=("EU", "BR"))
    await db_session.commit()
    assert (await client.get("/api/v1/auth/me", headers=_auth(w.james, "vendedor"))).json()["can_manage_prototypes"] is True
    assert (await client.get("/api/v1/auth/me", headers=_auth(w.plain, "vendedor"))).json()["can_manage_prototypes"] is False
    assert (await client.get("/api/v1/auth/me", headers=_auth(both, "vendedor", "EU"))).json()["can_manage_prototypes"] is True
    assert (await client.get("/api/v1/auth/me", headers=_auth(both, "vendedor", "BR"))).json()["can_manage_prototypes"] is False


# ── Auditoria da permissão ────────────────────────────────────────────────────

async def _events(db: AsyncSession, user, action: str):
    from app.models.privacy_event import PrivacyEvent
    return list((await db.execute(select(PrivacyEvent).where(
        PrivacyEvent.subject_id == user.id, PrivacyEvent.action == action,
    ))).scalars().all())


def _eu_access(flag: bool) -> dict:
    return {"market_accesses": [{
        "market_code": "EU", "role": "vendedor", "status": "active", "can_manage_prototypes": flag,
    }]}


async def test_mudar_a_permissao_e_auditado(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    headers = await _platform_headers(db_session)
    url = f"/api/v1/users/{w.plain.id}"
    assert (await client.patch(url, json=_eu_access(False), headers=headers)).status_code == 200
    assert await _events(db_session, w.plain, "prototype_access_granted") == []  # sem mudança, sem evento
    assert (await client.patch(url, json=_eu_access(True), headers=headers)).status_code == 200
    assert len(await _events(db_session, w.plain, "prototype_access_granted")) == 1
    assert (await client.patch(url, json=_eu_access(True), headers=headers)).status_code == 200
    assert len(await _events(db_session, w.plain, "prototype_access_granted")) == 1
    assert (await client.patch(url, json=_eu_access(False), headers=headers)).status_code == 200
    assert len(await _events(db_session, w.plain, "prototype_access_revoked")) == 1


async def test_criar_usuario_com_permissao_e_auditado(client: AsyncClient, db_session: AsyncSession):
    from app.models.user import User
    headers = await _platform_headers(db_session)
    created = await client.post(
        "/api/v1/users",
        json=_new_user("pr-aud@example.com", market_code="EU", can_manage_prototypes=True),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user = (await db_session.execute(select(User).where(User.email == "pr-aud@example.com"))).scalar_one()
    assert len(await _events(db_session, user, "prototype_access_granted")) == 1


async def test_somente_admin_da_plataforma_altera_a_permissao(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    url = f"/api/v1/users/{w.plain.id}"
    # Sessão comercial (mesmo admin do mercado) não administra identidades.
    assert (await client.patch(url, json=_eu_access(True), headers=_auth(w.admin, "admin"))).status_code in (401, 403)
    assert (await client.patch(url, json=_eu_access(True), headers=_auth(w.james, "vendedor"))).status_code in (401, 403)
    link = await db_session.get(UserMarket, (w.plain.id, "EU"))
    await db_session.refresh(link)
    assert link.can_manage_prototypes is False


# ── Migração de dados: James já marcado ───────────────────────────────────────

def _grant_to_james():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "prototypes_r45_20261111.py"
    spec = importlib.util.spec_from_file_location("prototypes_r45_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._grant_to_james


async def _run_grant(db: AsyncSession) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    grant = _grant_to_james()

    def run(sync_session):
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            grant()

    await db.run_sync(run)


async def _named(db, name: str, **kwargs):
    user = await make_user(db, email=f"mig-{uuid.uuid4().hex[:8]}@ilya-test.invalid", full_name=name,
                           role=UserRole.vendedor, home_market="EU")
    link = await make_user_market(db, user, market_code="EU", role="vendedor", **kwargs)
    return user, link


async def _flag(db: AsyncSession, user) -> bool:
    return (await db.execute(text(
        "SELECT can_manage_prototypes FROM user_markets WHERE user_id = :u AND market_code = 'EU'"
    ), {"u": user.id})).scalar_one()


async def test_migracao_liga_o_unico_james(db_session: AsyncSession):
    james, _ = await _named(db_session, "jAmEs Ferreira")
    outro, _ = await _named(db_session, "Maria Souza")
    await _run_grant(db_session)
    assert await _flag(db_session, james) is True
    assert await _flag(db_session, outro) is False


async def test_migracao_nao_faz_nada_com_zero_ou_mais_de_um(db_session: AsyncSession):
    outro, _ = await _named(db_session, "Maria Souza")
    await _run_grant(db_session)  # zero
    assert await _flag(db_session, outro) is False
    a, _ = await _named(db_session, "James Um")
    b, _ = await _named(db_session, "James Dois")
    await _run_grant(db_session)  # dois
    assert await _flag(db_session, a) is False and await _flag(db_session, b) is False


async def test_migracao_ignora_vinculo_inativo_e_conta_inativa(db_session: AsyncSession):
    suspended, _ = await _named(db_session, "James Suspenso", status="suspended")
    inactive, _ = await _named(db_session, "James Inativo")
    inactive.is_active = False
    await db_session.flush()
    alone, _ = await _named(db_session, "James Ativo")
    await _run_grant(db_session)
    assert await _flag(db_session, alone) is True  # os outros dois não contam
    assert await _flag(db_session, suspended) is False and await _flag(db_session, inactive) is False
