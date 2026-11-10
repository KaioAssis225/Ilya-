"""Galeria de fotos do produto (PostgreSQL real, disco local, sem MinIO).

Cobre as rotas novas (`/photos`), o espelho `products.photo_path`, o limite, o
RBAC/escopo de mercado, a exclusão segura do arquivo e a compatibilidade dos
endpoints legados (`upload-photo` substitui a principal; `DELETE /photo`).
"""
import io
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import media_orphans
from app.core.config import settings
from app.core.product_photos import MAX_PRODUCT_PHOTOS
from app.core.security import create_access_token
from app.models.market import VAT_PENDING, ProductMarket
from app.models.product import Product, ProductPhoto
from app.models.user import UserRole
from tests.factories import make_product, make_product_market, make_user, make_user_market

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/api/v1/products"


@pytest.fixture(autouse=True)
def disco(tmp_path, monkeypatch):
    raiz = tmp_path / "uploads"
    raiz.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(raiz))
    return raiz


def _png(cor: int = 90) -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (64, 48), (30, cor, 160)).save(saida, format="PNG")
    return saida.getvalue()


async def _headers(db: AsyncSession, market: str = "BR", role: str = "admin") -> dict[str, str]:
    user = await make_user(
        db, email=f"gal-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole(role), home_market=market,
    )
    await make_user_market(db, user, market_code=market, role=role)
    token = create_access_token(user.id, role, user.auth_version, market)
    return {"Authorization": f"Bearer {token}"}


async def _produto(db: AsyncSession, market: str = "BR", *, shared_with_br: bool = False) -> Product:
    produto = await make_product(db, market_code=market)
    await make_product_market(db, produto)
    if shared_with_br:
        db.add(ProductMarket(
            product_id=produto.id, market_code="BR", is_available=True, vat_rate=None,
            vat_status=VAT_PENDING, vat_source="import",
            approved_by_user_id=None, approved_at=None,
        ))
        await db.flush()
    return produto


async def _add(client: AsyncClient, headers, produto_id, cor: int = 90):
    return await client.post(
        f"{BASE}/{produto_id}/photos",
        files={"file": ("foto.png", _png(cor), "image/png")},
        headers=headers,
    )


async def _linhas(db: AsyncSession, produto_id) -> list[ProductPhoto]:
    result = await db.execute(
        select(ProductPhoto).where(ProductPhoto.product_id == produto_id)
        .order_by(ProductPhoto.position).execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _espelho(db: AsyncSession, produto: Product) -> str | None:
    await db.refresh(produto)
    return produto.photo_path


async def _tres_fotos(client, db, headers):
    produto = await _produto(db)
    for cor in (10, 20, 30):
        assert (await _add(client, headers, produto.id, cor)).status_code == 201
    return produto, await _linhas(db, produto.id)


# ── Adicionar ────────────────────────────────────────────────────────────────

async def test_primeira_foto_vira_principal_e_espelha_photo_path(client, db_session):
    headers, produto = await _headers(db_session), await _produto(db_session)

    resposta = await _add(client, headers, produto.id)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["photo_count"] == 1 and corpo["photos"][0]["is_primary"] is True
    assert corpo["photo_url"] and corpo["photos"][0]["thumbnail_url"]
    (linha,) = await _linhas(db_session, produto.id)
    assert await _espelho(db_session, produto) == linha.photo_path
    assert Path(linha.photo_path).exists()


async def test_segunda_foto_entra_no_fim_sem_mudar_a_principal(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)

    assert [f.position for f in linhas] == [0, 1, 2]
    assert [f.is_primary for f in linhas] == [True, False, False]
    assert await _espelho(db_session, produto) == linhas[0].photo_path


async def test_limite_de_fotos_retorna_409_sem_gravar_arquivo(client, db_session, disco):
    headers, produto = await _headers(db_session), await _produto(db_session)
    for cor in range(MAX_PRODUCT_PHOTOS):
        assert (await _add(client, headers, produto.id, cor)).status_code == 201
    antes = sorted(p.name for p in disco.rglob("*") if p.is_file())

    resposta = await _add(client, headers, produto.id, 200)

    assert resposta.status_code == 409
    assert len(await _linhas(db_session, produto.id)) == MAX_PRODUCT_PHOTOS
    assert sorted(p.name for p in disco.rglob("*") if p.is_file()) == antes


async def test_arquivo_invalido_e_rejeitado(client, db_session):
    headers, produto = await _headers(db_session), await _produto(db_session)

    resposta = await client.post(
        f"{BASE}/{produto.id}/photos",
        files={"file": ("foto.png", b"nao e imagem", "image/png")},
        headers=headers,
    )

    assert resposta.status_code == 422
    assert await _linhas(db_session, produto.id) == []


# ── Principal, ordem e remoção ───────────────────────────────────────────────

async def test_definir_principal_troca_flag_e_espelho(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)

    resposta = await client.put(f"{BASE}/{produto.id}/photos/{linhas[2].id}/primary", headers=headers)

    assert resposta.status_code == 200
    atuais = await _linhas(db_session, produto.id)
    assert [f.is_primary for f in atuais] == [False, False, True]
    assert await _espelho(db_session, produto) == linhas[2].photo_path
    primaria = next(f for f in resposta.json()["photos"] if f["is_primary"])
    assert primaria["id"] == str(linhas[2].id)


async def test_indice_parcial_impede_duas_principais(db_session):
    produto = await _produto(db_session)
    db_session.add_all([
        ProductPhoto(product_id=produto.id, photo_path="a.png", position=0, is_primary=True),
        ProductPhoto(product_id=produto.id, photo_path="b.png", position=1, is_primary=True),
    ])
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_reordenar_exige_o_conjunto_exato(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)
    ids = [str(f.id) for f in linhas]
    url = f"{BASE}/{produto.id}/photos/order"

    for invalido in (ids[:2], ids + [str(uuid.uuid4())], [ids[0], ids[0], ids[1]], [ids[0], ids[1], str(uuid.uuid4())]):
        resposta = await client.put(url, json={"photo_ids": invalido}, headers=headers)
        assert resposta.status_code == 422, invalido

    resposta = await client.put(url, json={"photo_ids": [ids[2], ids[0], ids[1]]}, headers=headers)
    assert resposta.status_code == 200
    assert [f["id"] for f in resposta.json()["photos"]] == [ids[2], ids[0], ids[1]]
    # A principal continua a mesma, mesmo mudando de posição.
    assert await _espelho(db_session, produto) == linhas[0].photo_path


async def test_remover_a_principal_promove_a_proxima_e_apaga_o_arquivo(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)

    resposta = await client.delete(f"{BASE}/{produto.id}/photos/{linhas[0].id}", headers=headers)

    assert resposta.status_code == 200
    restantes = await _linhas(db_session, produto.id)
    assert [f.position for f in restantes] == [0, 1]
    assert restantes[0].is_primary and restantes[0].photo_path == linhas[1].photo_path
    assert await _espelho(db_session, produto) == linhas[1].photo_path
    assert not Path(linhas[0].photo_path).exists()
    assert Path(linhas[1].photo_path).exists()


async def test_remover_a_ultima_foto_zera_photo_path(client, db_session):
    headers, produto = await _headers(db_session), await _produto(db_session)
    await _add(client, headers, produto.id)
    (linha,) = await _linhas(db_session, produto.id)

    resposta = await client.delete(f"{BASE}/{produto.id}/photos/{linha.id}", headers=headers)

    assert resposta.status_code == 200 and resposta.json()["photo_url"] is None
    assert await _linhas(db_session, produto.id) == []
    assert await _espelho(db_session, produto) is None


async def test_foto_inexistente_ou_de_outro_produto_da_404(client, db_session):
    headers = await _headers(db_session)
    produto, _ = await _tres_fotos(client, db_session, headers)
    outro = await _produto(db_session)
    await _add(client, headers, outro.id)
    (alheia,) = await _linhas(db_session, outro.id)

    for foto_id in (uuid.uuid4(), alheia.id):
        assert (await client.delete(f"{BASE}/{produto.id}/photos/{foto_id}", headers=headers)).status_code == 404
        assert (await client.put(f"{BASE}/{produto.id}/photos/{foto_id}/primary", headers=headers)).status_code == 404
    assert len(await _linhas(db_session, produto.id)) == 3


# ── Arquivo só sai se ninguém mais usa ───────────────────────────────────────

async def test_arquivo_usado_por_outro_produto_nao_e_apagado(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)
    outro = await _produto(db_session)
    outro.photo_path = linhas[1].photo_path  # outro produto cita o mesmo arquivo
    await db_session.flush()

    resposta = await client.delete(f"{BASE}/{produto.id}/photos/{linhas[1].id}", headers=headers)

    assert resposta.status_code == 200
    assert Path(linhas[1].photo_path).exists()


async def test_snapshot_de_pedido_em_json_protege_a_foto_da_galeria(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)
    await db_session.execute(text("CREATE TABLE zz_snapshot_galeria (payload jsonb)"))
    await db_session.execute(
        text("INSERT INTO zz_snapshot_galeria VALUES (CAST(:p AS jsonb))"),
        {"p": '{"products":[{"photo_path":"%s"}]}' % linhas[2].photo_path.replace("\\", "\\\\")},
    )

    await client.delete(f"{BASE}/{produto.id}/photos/{linhas[2].id}", headers=headers)

    assert Path(linhas[2].photo_path).exists()


async def test_foto_so_na_galeria_conta_como_referenciada(db_session):
    produto = await _produto(db_session)
    caminho = f"object://eu-products/{uuid.uuid4()}.png"
    db_session.add(ProductPhoto(product_id=produto.id, photo_path=caminho, position=0, is_primary=False))
    await db_session.flush()

    assert await media_orphans.is_upload_referenced(db_session, caminho) is True
    refs = await media_orphans.scan_photo_references(db_session)
    assert caminho.rsplit("/", 1)[-1].split(".")[0] in refs.uuids


# ── RBAC e mercado ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "vendedor", "produtos"])
async def test_papeis_que_editam_produto_podem_gerenciar_fotos(client, db_session, role):
    headers, produto = await _headers(db_session, role=role), await _produto(db_session)

    assert (await _add(client, headers, produto.id)).status_code == 201


@pytest.mark.parametrize("role", ["cadastros", "executivo"])
async def test_papeis_sem_permissao_recebem_403_em_todas_as_rotas(client, db_session, role):
    admin = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, admin)
    negado = await _headers(db_session, role=role)
    pid, fid = produto.id, linhas[0].id

    respostas = [
        await _add(client, negado, pid),
        await client.delete(f"{BASE}/{pid}/photos/{fid}", headers=negado),
        await client.put(f"{BASE}/{pid}/photos/order", json={"photo_ids": [str(fid)]}, headers=negado),
        await client.put(f"{BASE}/{pid}/photos/{fid}/primary", headers=negado),
    ]

    assert [r.status_code for r in respostas] == [403, 403, 403, 403]
    assert len(await _linhas(db_session, pid)) == 3


async def test_sem_token_recebe_401(client, db_session):
    produto = await _produto(db_session)

    resposta = await client.post(
        f"{BASE}/{produto.id}/photos", files={"file": ("f.png", _png(), "image/png")}
    )

    assert resposta.status_code == 401


async def test_produto_de_outro_mercado_da_404(client, db_session):
    produto_br = await _produto(db_session, "BR")
    eu = await _headers(db_session, "EU")

    assert (await _add(client, eu, produto_br.id)).status_code == 404
    assert await _linhas(db_session, produto_br.id) == []


async def test_produto_eu_compartilhado_com_br_da_403_nas_mutacoes(client, db_session):
    produto = await _produto(db_session, "EU", shared_with_br=True)
    eu = await _headers(db_session, "EU")
    foto = ProductPhoto(product_id=produto.id, photo_path="x.png", position=0, is_primary=True)
    db_session.add(foto)
    produto.photo_path = "x.png"
    await db_session.flush()

    respostas = [
        await _add(client, eu, produto.id),
        await client.delete(f"{BASE}/{produto.id}/photos/{foto.id}", headers=eu),
        await client.put(f"{BASE}/{produto.id}/photos/{foto.id}/primary", headers=eu),
        await client.put(f"{BASE}/{produto.id}/photos/order", json={"photo_ids": [str(foto.id)]}, headers=eu),
        await client.post(
            f"{BASE}/{produto.id}/upload-photo", files={"file": ("f.png", _png(), "image/png")}, headers=eu
        ),
    ]

    assert [r.status_code for r in respostas] == [403] * 5


async def test_galeria_eu_grava_no_prefixo_do_mercado(client, db_session, disco):
    produto, eu = await _produto(db_session, "EU"), await _headers(db_session, "EU")

    assert (await _add(client, eu, produto.id)).status_code == 201

    (linha,) = await _linhas(db_session, produto.id)
    assert (disco / "eu") in Path(linha.photo_path).parents


# ── Legado ───────────────────────────────────────────────────────────────────

async def test_upload_legado_substitui_a_principal_e_preserva_as_extras(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)

    resposta = await client.post(
        f"{BASE}/{produto.id}/upload-photo",
        files={"file": ("nova.png", _png(200), "image/png")},
        headers=headers,
    )

    assert resposta.status_code == 200
    atuais = await _linhas(db_session, produto.id)
    assert len(atuais) == 3
    assert atuais[0].is_primary and atuais[0].photo_path not in {f.photo_path for f in linhas}
    assert [f.photo_path for f in atuais[1:]] == [linhas[1].photo_path, linhas[2].photo_path]
    assert await _espelho(db_session, produto) == atuais[0].photo_path
    assert not Path(linhas[0].photo_path).exists() and Path(linhas[1].photo_path).exists()


async def test_upload_legado_em_produto_sem_foto_cria_a_principal(client, db_session):
    headers, produto = await _headers(db_session), await _produto(db_session)

    resposta = await client.post(
        f"{BASE}/{produto.id}/upload-photo",
        files={"file": ("nova.png", _png(), "image/png")},
        headers=headers,
    )

    assert resposta.status_code == 200 and resposta.json()["photo_count"] == 1


async def test_delete_legado_remove_a_principal_e_promove_a_proxima(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)

    resposta = await client.delete(f"{BASE}/{produto.id}/photo", headers=headers)

    assert resposta.status_code == 200
    assert resposta.json()["photo_count"] == 2
    assert await _espelho(db_session, produto) == linhas[1].photo_path


# ── Cura e leitura ───────────────────────────────────────────────────────────

async def test_photo_path_gravado_pela_api_antiga_vira_a_principal(client, db_session):
    """Janela de deploy: a API anterior gravou só `photo_path`."""
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)
    nova = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4()}.png"
    nova.write_bytes(_png())
    produto.photo_path = str(nova)
    await db_session.flush()

    resposta = await client.put(f"{BASE}/{produto.id}/photos/{linhas[1].id}/primary", headers=headers)

    assert resposta.status_code == 200
    atuais = await _linhas(db_session, produto.id)
    assert len(atuais) == 4 and sum(f.is_primary for f in atuais) == 1
    assert await _espelho(db_session, produto) == linhas[1].photo_path


async def test_listagem_traz_a_galeria_e_a_principal_nos_campos_antigos(client, db_session):
    headers = await _headers(db_session)
    produto, linhas = await _tres_fotos(client, db_session, headers)
    await client.put(f"{BASE}/{produto.id}/photos/{linhas[1].id}/primary", headers=headers)

    resposta = await client.get(f"{BASE}/{produto.id}", headers=headers)

    corpo = resposta.json()
    assert corpo["photo_count"] == 3 and len(corpo["photos"]) == 3
    principal = next(f for f in corpo["photos"] if f["is_primary"])
    assert principal["photo_url"] == corpo["photo_url"]
    assert principal["thumbnail_url"] == corpo["thumbnail_url"]
