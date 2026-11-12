"""Atalho do orçamento: achar o protótipo digitando o código ou o nome.

PostgreSQL real, dados sintéticos. `GET /products?include_prototypes=true&q=...`
só devolve protótipo ao DONO com a permissão no mercado EU; para os demais o
parâmetro é ignorado e o servidor decide pela permissão, não pelo pedido.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import UserMarket
from tests.integration.test_prototypes import PROTOTYPES, _auth, _create, _person, _world
from tests.integration.test_prototypes_orcamento import _normal_product

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PRODUCTS = "/api/v1/products"


async def _search(client: AsyncClient, headers: dict, q: str | None, *, include: bool = True, **extra):
    params: dict = {"limit": 50, **extra}
    if q is not None:
        params["q"] = q
    if include:
        params["include_prototypes"] = "true"
    return await client.get(PRODUCTS, params=params, headers=headers)


def _codes(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["product_code"] for row in response.json()]


async def test_com_permissao_acha_pelo_codigo_exato_parcial_e_sem_diferenciar_caixa(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    code = proto["product_code"]
    james = _auth(w.james, "vendedor")
    # Parcial: o começo do código (ex.: "PROT-00"), em qualquer caixa.
    for query in (code, code.lower(), code.upper(), code[:7], code[:7].lower(), "PROT", code[:-1]):
        found = await _search(client, james, query)
        assert code in _codes(found), query
    [row] = [r for r in (await _search(client, james, code)).json() if r["product_code"] == code]
    assert row["is_prototype"] is True and row["market_code"] == "EU"
    assert row["market_prices"]["pvp"] == "1500.00" and row["vat_rate"] == "23.00"


async def test_acha_pelo_nome_em_portugues_e_em_ingles(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w, description_pt_pt="Poltrona azul-petróleo", description_en="Teal armchair")
    james = _auth(w.james, "vendedor")
    assert proto["product_code"] in _codes(await _search(client, james, "azul-petr"))
    # O nome em inglês vale quando a tela está em inglês (como no catálogo).
    assert proto["product_code"] in _codes(await _search(client, james, "teal arm", language="en-GB"))
    assert proto["product_code"] not in _codes(await _search(client, james, "mesa de jantar"))


async def test_mistura_com_produtos_comuns_quando_o_texto_bate_nos_dois(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w, description_pt_pt="Poltrona Baía protótipo")
    normal = await _normal_product(db_session, w)
    normal.description = "Poltrona Baía"
    await db_session.commit()
    codes = _codes(await _search(client, _auth(w.james, "vendedor"), "poltrona ba"))
    assert proto["product_code"] in codes and normal.product_code in codes


async def test_sem_o_parametro_ou_sem_texto_o_protótipo_nao_aparece(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    code = proto["product_code"]
    james = _auth(w.james, "vendedor")
    assert code not in _codes(await _search(client, james, code, include=False))      # catálogo comum
    assert code not in _codes(await _search(client, james, None))                      # sem texto
    assert code not in _codes(await _search(client, james, "   "))                     # texto em branco
    assert (await client.get(f"{PRODUCTS}?include_prototypes=false&q={code}", headers=james)).json() == []


async def test_sem_permissao_nunca_acha_nem_por_codigo_exato(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    code, name = proto["product_code"], "Poltrona protótipo"
    for who, role in ((w.plain, "vendedor"), (w.admin, "admin"), (w.other, "vendedor")):
        headers = _auth(who, role)
        for query in (code, code.lower(), "PROT-00", name):
            response = await _search(client, headers, query)
            assert response.status_code == 200
            assert proto["id"] not in {r["id"] for r in response.json()}, (role, query)
            assert code not in response.text


async def test_perder_a_permissao_fecha_a_busca(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    assert proto["product_code"] in _codes(await _search(client, james, proto["product_code"]))
    link = await db_session.get(UserMarket, (w.james.id, "EU"))
    link.can_manage_prototypes = False
    await db_session.commit()
    assert proto["product_code"] not in _codes(await _search(client, james, proto["product_code"]))


async def test_no_mercado_br_nao_acha(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    both = await _person(db_session, "ambos", prototypes=True, markets=("EU", "BR"))
    own = await client.post(PROTOTYPES, json=w.body(), headers=_auth(both, "vendedor", "EU"))
    assert own.status_code == 201
    own_code = own.json()["product_code"]
    await db_session.commit()
    assert own_code in _codes(await _search(client, _auth(both, "vendedor", "EU"), own_code))
    # Na sessão BR do mesmo usuário (inclusive do próprio protótipo): nada.
    in_br = await _search(client, _auth(both, "vendedor", "BR"), own_code)
    assert in_br.status_code == 200 and own_code not in in_br.text
    other_in_br = await _search(client, _auth(both, "vendedor", "BR"), proto["product_code"])
    assert proto["product_code"] not in other_in_br.text


async def test_protótipo_com_grupo_proprio_aparece_inteiro_na_busca(client: AsyncClient, db_session: AsyncSession):
    """A resposta completa (aplicações com a categoria do grupo próprio) não pode quebrar."""
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    group = (await client.post(
        f"{PROTOTYPES}/{proto['id']}/optional-groups",
        json={"name": "Tampo", "options": [{"name": "Carvalho"}, {"name": "Nogueira"}]}, headers=james,
    )).json()
    patched = await client.patch(
        f"{PROTOTYPES}/{proto['id']}",
        json={"optional_applications": [{"category_id": group["id"], "name": "Tampo", "allow_all": True}]},
        headers=james,
    )
    assert patched.status_code == 200, patched.text
    found = await _search(client, james, proto["product_code"])
    [row] = [r for r in found.json() if r["product_code"] == proto["product_code"]]
    [application] = row["optional_applications"]
    assert application["category_name"] == "Tampo"
    # Depois da busca a visão do dono é fechada: o catálogo comum não vaza.
    assert proto["product_code"] not in _codes(await _search(client, james, proto["product_code"], include=False))


async def test_contagem_total_inclui_o_protótipo_achado(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    with_it = await client.get(PRODUCTS, params={"q": proto["product_code"], "include_prototypes": "true"}, headers=james)
    without = await client.get(PRODUCTS, params={"q": proto["product_code"]}, headers=james)
    assert with_it.headers["X-Total-Count"] == "1" and without.headers["X-Total-Count"] == "0"
