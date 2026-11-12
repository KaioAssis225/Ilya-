"""Foto do protótipo: upload, miniatura, mídia assinada e quem enxerga a URL.

PostgreSQL real, disco local, imagens sintéticas. A rota de mídia não conhece
usuário: autoriza pela assinatura HMAC da URL (chave aleatória + validade), e a
URL só sai nas respostas que já passaram por permissão e dono. Estes testes
provam as duas pontas: a URL do dono funciona e a dos outros nunca existe.
"""
import re

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_prototypes import PROTOTYPES, _auth, _create, _png, _world
from tests.integration.test_prototypes_orcamento import _eu_client, _quote

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _upload(client: AsyncClient, proto_id: str, headers: dict, name: str = "foto.png"):
    return await client.post(
        f"{PROTOTYPES}/{proto_id}/photos", files={"file": (name, _png(), "image/png")}, headers=headers,
    )


async def test_foto_do_dono_aparece_no_protótipo_com_miniatura(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    assert proto["photo_url"] is None and proto["photos"] == []
    james = _auth(w.james, "vendedor")
    response = await _upload(client, proto["id"], james)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["photo_url"] and body["thumbnail_url"]
    [photo] = body["photos"]
    assert photo["is_primary"] is True and photo["photo_url"] == body["photo_url"]
    # A lista da aba Protótipos e o GET trazem a miniatura.
    listed = (await client.get(PROTOTYPES, headers=james)).json()
    assert listed[0]["thumbnail_url"] and listed[0]["photo_count"] == 1
    single = (await client.get(f"{PROTOTYPES}/{proto['id']}", headers=james)).json()
    assert single["thumbnail_url"]


async def test_url_assinada_da_foto_entrega_a_imagem(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    body = (await _upload(client, proto["id"], james)).json()
    for url in (body["photo_url"], body["thumbnail_url"]):
        fetched = await client.get(url)
        assert fetched.status_code == 200, url
        # Em disco local o tipo vem do sistema operacional; a prova é a imagem em si.
        assert fetched.content[:4] in (b"\x89PNG", b"RIFF", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xdb")
        assert fetched.headers["cache-control"].startswith("private")
        assert fetched.content
    # Assinatura adulterada ou ausente: nada de imagem.
    tampered = re.sub(r"signature=[0-9a-f]+", "signature=" + "0" * 64, body["photo_url"])
    assert (await client.get(tampered)).status_code == 403
    without_signature = body["photo_url"].split("&signature=")[0]
    assert (await client.get(without_signature)).status_code == 422


async def test_a_url_da_foto_nao_vaza_para_quem_nao_e_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    url = (await _upload(client, proto["id"], james)).json()["photo_url"]
    code = proto["product_code"]
    for who, role in ((w.other, "vendedor"), (w.plain, "vendedor"), (w.admin, "admin")):
        headers = _auth(who, role)
        responses = [
            await client.get(f"{PROTOTYPES}/{proto['id']}", headers=headers),
            await client.get(PROTOTYPES, headers=headers),
            await client.get("/api/v1/products", params={"limit": 1000}, headers=headers),
            await client.get(f"/api/v1/products/{proto['id']}", headers=headers),
            await client.post("/api/v1/products/batch", json={"product_codes": [code]}, headers=headers),
        ]
        for response in responses:
            assert url not in response.text and code not in response.text, (role, response.request.url)
        assert (await _upload(client, proto["id"], headers)).status_code == 404


async def test_troca_remocao_e_principal_pela_api_do_protótipo(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    first = (await _upload(client, proto["id"], james)).json()
    second = (await _upload(client, proto["id"], james, "segunda.png")).json()
    assert second["photo_count"] == 2
    assert second["photo_url"] == first["photo_url"]  # a primeira segue principal
    other = next(p for p in second["photos"] if not p["is_primary"])
    swapped = (await client.put(f"{PROTOTYPES}/{proto['id']}/photos/{other['id']}/primary", headers=james)).json()
    assert swapped["photo_url"] == other["photo_url"]
    removed = (await client.delete(f"{PROTOTYPES}/{proto['id']}/photos/{other['id']}", headers=james)).json()
    assert removed["photo_count"] == 1 and removed["photo_url"] != other["photo_url"]


async def test_limite_de_dez_fotos(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    for _ in range(10):
        assert (await _upload(client, proto["id"], james)).status_code == 201
    assert (await _upload(client, proto["id"], james)).status_code == 409


async def test_foto_principal_chega_ao_item_do_orcamento_do_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    photo_url = (await _upload(client, proto["id"], james)).json()["photo_url"]
    eu_client = await _eu_client(db_session)
    assert (await _quote(client, w.james, eu_client, proto["product_code"])).status_code == 201
    # A tela de orçamento/pedido resolve a foto de cada linha pelo /products/batch.
    batch = await client.post("/api/v1/products/batch", json={"product_codes": [proto["product_code"]]}, headers=james)
    [item] = batch.json()
    assert item["photo_url"] and item["thumbnail_url"] and item["photo_url"].split("?")[0] == photo_url.split("?")[0]
