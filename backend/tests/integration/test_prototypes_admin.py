"""Admin do mercado EU vê e usa protótipos sempre; os demais seguem a liberação.

Regra única (MarketActor.can_manage_prototypes): mercado EU e papel `admin` no
vínculo EU, OU a liberação por usuário (`can_manage_prototypes`) com papel
admin/vendedor/produtos. O admin enxerga e opera os protótipos de TODOS; quem foi
liberado, só os próprios. BR nunca. PostgreSQL real, dados sintéticos.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.order import Order
from app.models.user import UserRole
from app.services.order_email_jobs import _snapshot_v2
from tests.factories import make_product, make_product_market, make_representative, make_user, make_user_market
from tests.integration.test_prototypes import PROTOTYPES, _auth, _create, _person, _png, _world
from tests.integration.test_prototypes_orcamento import ORDERS, _eu_client, _quote

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PRODUCTS = "/api/v1/products"


async def _search(client: AsyncClient, headers: dict, q: str, **extra):
    return await client.get(PRODUCTS, params={"q": q, "include_prototypes": "true", "limit": 15, **extra}, headers=headers)


def _codes(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["product_code"] for row in response.json()]


async def _rep_eu(db: AsyncSession):
    rep = await make_representative(db, market_code="EU", name=f"Rep {uuid.uuid4().hex[:5]}")
    user = await make_user(
        db, email=f"pr-rep-{uuid.uuid4().hex[:6]}@ilya-test.invalid", role=UserRole.representante, home_market="EU",
    )
    user.rep_id = rep.id
    await make_user_market(db, user, market_code="EU", role="representante", rep_id=rep.id)
    await db.commit()
    return user


# ── Quem tem acesso ───────────────────────────────────────────────────────────

async def test_auth_me_admin_eu_tem_acesso_sem_a_liberacao_e_admin_br_nao(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    both = await _person(db_session, "admin-ambos", role="admin", markets=("EU", "BR"))
    await db_session.commit()

    async def me(user, role, market="EU"):
        return (await client.get("/api/v1/auth/me", headers=_auth(user, role, market))).json()["can_manage_prototypes"]

    assert await me(w.admin, "admin") is True
    assert await me(both, "admin", "EU") is True
    assert await me(both, "admin", "BR") is False
    assert await me(w.plain, "vendedor") is False
    assert await me(w.nobody, "produtos") is False
    assert await me(w.james, "vendedor") is True


async def test_admin_so_no_vinculo_br_nao_tem_acesso_no_eu(client: AsyncClient, db_session: AsyncSession):
    """O papel que vale é o do vínculo EU: admin no BR e vendedor no EU não abre a área."""
    w = await _world(db_session)
    user = await make_user(db_session, email=f"pr-mix-{uuid.uuid4().hex[:6]}@ilya-test.invalid", role=UserRole.admin, home_market="BR")
    await make_user_market(db_session, user, market_code="BR", role="admin")
    await make_user_market(db_session, user, market_code="EU", role="vendedor")
    await db_session.commit()
    proto = await _create(client, w)
    headers = _auth(user, "vendedor", "EU")
    assert (await client.get(PROTOTYPES, headers=headers)).status_code == 404
    assert proto["product_code"] not in (await _search(client, headers, "prot")).text


async def test_representante_eu_sem_a_liberacao_nao_acha_nem_acessa(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    rep = await _rep_eu(db_session)
    headers = _auth(rep, "representante")
    for query in ("prot", "PROT-0", proto["product_code"], proto["product_code"].lower()):
        found = await _search(client, headers, query)
        assert found.status_code == 200 and proto["product_code"] not in found.text, query
    assert (await client.get(PROTOTYPES, headers=headers)).status_code == 404
    assert (await client.get(f"{PROTOTYPES}/{proto['id']}", headers=headers)).status_code == 404
    batch = await client.post(f"{PRODUCTS}/batch", json={"product_codes": [proto["product_code"]]}, headers=headers)
    assert batch.json() == []
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["can_manage_prototypes"] is False


# ── Busca do orçamento ────────────────────────────────────────────────────────

async def test_admin_eu_acha_por_prot_parcial_codigo_e_nome_sem_diferenciar_caixa(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w, description_pt_pt="Poltrona Baía protótipo")  # do James, não do admin
    code = proto["product_code"]
    admin = _auth(w.admin, "admin")
    for query in ("prot", "PROT", "Prot-0", code[:7], code[:7].lower(), code, code.lower(), "poltrona ba"):
        assert code in _codes(await _search(client, admin, query)), query
    # Sem texto ou sem o parâmetro, o catálogo comum segue sem protótipo, até para o admin.
    assert code not in _codes(await client.get(PRODUCTS, params={"limit": 100}, headers=admin))
    assert code not in _codes(await client.get(PRODUCTS, params={"q": code}, headers=admin))
    assert code not in _codes(await client.get(PRODUCTS, params={"include_prototypes": "true"}, headers=admin))


async def test_admin_br_nao_acha(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    both = await _person(db_session, "admin-br", role="admin", markets=("EU", "BR"))
    await db_session.commit()
    headers = _auth(both, "admin", "BR")
    found = await _search(client, headers, "prot")
    assert found.status_code == 200 and proto["product_code"] not in found.text
    assert (await client.get(PROTOTYPES, headers=headers)).status_code == 404


async def test_a_busca_traz_protótipos_primeiro_mesmo_com_muitos_produtos_comuns(client: AsyncClient, db_session: AsyncSession):
    """O limite da página (15) não pode cortar o protótipo quando muitos produtos batem com 'prot'."""
    w = await _world(db_session)
    proto = await _create(client, w)
    for index in range(16):
        product = await make_product(
            db_session, market_code="EU", catalog=w.catalog, product_code=f"AAA-{index:02d}", description="Protetor comum",
        )
        await make_product_market(db_session, product)
    await db_session.commit()
    codes = _codes(await _search(client, _auth(w.admin, "admin"), "prot"))
    assert len(codes) == 15 and codes[0] == proto["product_code"]


# ── Área de protótipos do admin ───────────────────────────────────────────────

async def test_admin_lista_ve_edita_e_desativa_protótipos_de_qualquer_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    from_james = await _create(client, w)
    from_other = await _create(client, w, who=w.other, description_pt_pt="Do outro")
    admin = _auth(w.admin, "admin")
    listed = await client.get(PROTOTYPES, headers=admin)
    assert {from_james["id"], from_other["id"]} <= {row["id"] for row in listed.json()}
    assert (await client.get(f"{PROTOTYPES}/{from_james['id']}", headers=admin)).status_code == 200
    patched = await client.patch(f"{PROTOTYPES}/{from_james['id']}", json={"observacao": "revisado pelo admin"}, headers=admin)
    assert patched.status_code == 200 and patched.json()["observacao"] == "revisado pelo admin"
    photo = await client.post(
        f"{PROTOTYPES}/{from_james['id']}/photos", files={"file": ("a.png", _png(), "image/png")}, headers=admin,
    )
    assert photo.status_code == 201 and photo.json()["thumbnail_url"]
    group = await client.post(
        f"{PROTOTYPES}/{from_james['id']}/optional-groups", json={"name": "Tampo", "options": [{"name": "Carvalho"}]}, headers=admin,
    )
    assert group.status_code == 201
    assert (await client.delete(f"{PROTOTYPES}/{from_other['id']}", headers=admin)).status_code == 204
    # O dono continua só com os dele.
    james_ids = {row["id"] for row in (await client.get(PROTOTYPES, headers=_auth(w.james, "vendedor"))).json()}
    assert james_ids == {from_james["id"]}


async def test_admin_cria_protótipo_proprio_e_o_outro_usuario_nao_o_ve(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    created = await client.post(PROTOTYPES, json=w.body(), headers=_auth(w.admin, "admin"))
    assert created.status_code == 201, created.text
    assert created.json()["product_code"].startswith("PROT-")
    assert (await client.get(f"{PROTOTYPES}/{created.json()['id']}", headers=_auth(w.james, "vendedor"))).status_code == 404


async def test_catalogo_e_listas_gerais_seguem_sem_protótipo_ate_para_o_admin(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    group = (await client.post(
        f"{PROTOTYPES}/{proto['id']}/optional-groups", json={"name": "Tampo", "options": [{"name": "Carvalho"}]},
        headers=_auth(w.james, "vendedor"),
    )).json()
    admin = _auth(w.admin, "admin")
    assert (await client.get(f"{PRODUCTS}/{proto['id']}", headers=admin)).status_code == 404
    assert proto["product_code"] not in (await client.get(PRODUCTS, params={"limit": 1000}, headers=admin)).text
    assert group["id"] not in {c["id"] for c in (await client.get("/api/v1/optional-categories", headers=admin)).json()}
    listed = {o["id"] for o in (await client.get("/api/v1/optionals", params={"limit": 1000}, headers=admin)).json()}
    assert not {o["id"] for o in group["options"]} & listed


# ── Orçamento ─────────────────────────────────────────────────────────────────

async def test_admin_usa_protótipo_de_outro_no_orcamento_edita_e_gera_o_pdf(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w, vat_rate="6.00")
    james = _auth(w.james, "vendedor")
    assert (await client.post(
        f"{PROTOTYPES}/{proto['id']}/photos", files={"file": ("a.png", _png(), "image/png")}, headers=james,
    )).status_code == 201
    eu_client = await _eu_client(db_session)
    admin = _auth(w.admin, "admin")

    created = await _quote(client, w.admin, eu_client, proto["product_code"], role="admin")
    assert created.status_code == 201, created.text
    item = created.json()["items"][0]
    assert item["product_code"] == proto["product_code"] and str(item["ipi_rate"]) in ("6.00", "6")
    order_id = created.json()["id"]

    batch = await client.post(f"{PRODUCTS}/batch", json={"product_codes": [proto["product_code"]]}, headers=admin)
    assert [p["product_code"] for p in batch.json()] == [proto["product_code"]] and batch.json()[0]["thumbnail_url"]

    # O pedido do admin com o protótipo do James tem a foto no PDF/e-mail.
    order = (await db_session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
    fresh = (await db_session.execute(
        select(Client).where(Client.id == eu_client.id).execution_options(populate_existing=True)
    )).scalar_one()
    snapshot = await _snapshot_v2(db_session, order, fresh, None, None, None)
    assert snapshot["products"][0]["photo_path"]

    edited = await client.put(
        f"{ORDERS}/{order_id}",
        json={"price_list_code": "pvp", "items": [{"product_code": proto["product_code"], "qty": 3}]},
        headers=admin,
    )
    assert edited.status_code == 200, edited.text


async def test_quem_nao_tem_acesso_continua_sem_poder_orcar(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    eu_client = await _eu_client(db_session)
    rep = await _rep_eu(db_session)
    for who, role in ((w.plain, "vendedor"), (w.nobody, "produtos"), (rep, "representante")):
        response = await _quote(client, who, eu_client, proto["product_code"], role=role)
        assert response.status_code in (403, 404), (role, response.text)
