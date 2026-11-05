"""Trocar/remover a foto de um produto NÃO apaga o arquivo que outra linha ainda usa.

Caso real: vários produtos EU apontavam para o mesmo objeto de foto. Trocar o
produto A apagava o arquivo ainda usado por B, C... e por snapshots de pedido.
Aqui, com PostgreSQL real e disco local (sem MinIO):

- dois produtos com o mesmo `photo_path`: trocar um mantém o arquivo; trocar o
  segundo (último uso) apaga;
- o mesmo vale para `DELETE .../photo` e para opcionais;
- snapshot de pedido (JSON) que cita o arquivo impede o apagamento;
- erro na checagem -> o arquivo fica.
"""
import io
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import media_orphans
from app.core import uploads as uploads_module
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from tests.factories import make_product, make_product_market, make_user, make_user_market
from tests.factories.optionals import make_optional, make_optional_category

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def disco(tmp_path, monkeypatch):
    raiz = tmp_path / "uploads"
    raiz.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(raiz))
    apagados: list[str] = []
    original = uploads_module._delete_upload

    def espiao(path):
        apagados.append(path)
        original(path)

    monkeypatch.setattr(uploads_module, "_delete_upload", espiao)
    return raiz, apagados


def _foto_antiga(raiz: Path, pasta: str = "") -> Path:
    destino = raiz / pasta if pasta else raiz
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{uuid.uuid4()}.png"
    arquivo.write_bytes(b"foto antiga")
    return arquivo


def _png() -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 90, 160)).save(saida, format="PNG")
    return saida.getvalue()


async def _admin(db: AsyncSession) -> dict[str, str]:
    user = await make_user(
        db, email=f"foto-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.admin, home_market="BR",
    )
    await make_user_market(db, user, market_code="BR", role="admin")
    token = create_access_token(user.id, "admin", user.auth_version, "BR")
    return {"Authorization": f"Bearer {token}"}


async def _produto(db: AsyncSession, foto: Path):
    produto = await make_product(db, market_code="BR")
    await make_product_market(db, produto)
    produto.photo_path = str(foto)
    await db.flush()
    return produto


async def _trocar(client: AsyncClient, headers, produto_id):
    return await client.post(
        f"/api/v1/products/{produto_id}/upload-photo",
        files={"file": ("nova.png", _png(), "image/png")},
        headers=headers,
    )


async def test_dois_produtos_com_a_mesma_foto_so_apaga_no_ultimo_uso(
    client: AsyncClient, db_session: AsyncSession, disco
):
    raiz, apagados = disco
    antiga = _foto_antiga(raiz)
    a, b = await _produto(db_session, antiga), await _produto(db_session, antiga)
    headers = await _admin(db_session)

    assert (await _trocar(client, headers, a.id)).status_code == 200
    assert antiga.exists(), "B ainda usa o arquivo: não pode ser apagado"
    assert str(antiga) not in apagados

    assert (await _trocar(client, headers, b.id)).status_code == 200
    assert not antiga.exists(), "último uso trocado: o arquivo antigo pode sair"
    assert str(antiga) in apagados


async def test_remover_foto_de_um_produto_mantem_o_arquivo_usado_por_outro(
    client: AsyncClient, db_session: AsyncSession, disco
):
    raiz, apagados = disco
    antiga = _foto_antiga(raiz)
    a, b = await _produto(db_session, antiga), await _produto(db_session, antiga)
    headers = await _admin(db_session)

    resposta = await client.delete(f"/api/v1/products/{a.id}/photo", headers=headers)
    assert resposta.status_code == 200 and antiga.exists()
    resposta = await client.delete(f"/api/v1/products/{b.id}/photo", headers=headers)
    assert resposta.status_code == 200 and not antiga.exists()


async def test_snapshot_de_pedido_em_json_impede_o_apagamento(
    client: AsyncClient, db_session: AsyncSession, disco
):
    raiz, apagados = disco
    antiga = _foto_antiga(raiz)
    produto = await _produto(db_session, antiga)
    await db_session.execute(text("CREATE TABLE zz_snapshot (id int, doc jsonb)"))
    await db_session.execute(
        text("INSERT INTO zz_snapshot VALUES (1, CAST(:doc AS jsonb))"),
        {"doc": '{"products": [{"product_code": "X", "photo_path": "%s"}]}'
                % str(antiga).replace("\\", "\\\\")},
    )
    headers = await _admin(db_session)

    assert (await _trocar(client, headers, produto.id)).status_code == 200
    assert antiga.exists(), "o snapshot do pedido ainda cita o arquivo"
    assert str(antiga) not in apagados


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
async def test_opcionais_tambem_protegem_foto_compartilhada(
    client: AsyncClient, db_session: AsyncSession, disco
):
    raiz, apagados = disco
    antiga = _foto_antiga(raiz, "optionals")
    categoria = await make_optional_category(db_session, market_code="BR")
    o1 = await make_optional(db_session, categoria, color_name="Cor 1", market_code="BR")
    o2 = await make_optional(db_session, categoria, color_name="Cor 2", market_code="BR")
    o1.photo_path = o2.photo_path = str(antiga)
    await db_session.flush()
    headers = await _admin(db_session)

    async def trocar(opcional):
        return await client.post(
            f"/api/v1/optionals/{opcional.id}/upload-photo",
            files={"file": ("nova.png", _png(), "image/png")},
            headers=headers,
        )

    assert (await trocar(o1)).status_code == 200
    assert antiga.exists()
    assert (await trocar(o2)).status_code == 200
    assert not antiga.exists()


async def test_erro_na_checagem_nao_apaga(
    db_session: AsyncSession, disco, monkeypatch
):
    raiz, apagados = disco
    antiga = _foto_antiga(raiz)
    monkeypatch.setattr(
        media_orphans, "_REFERENCE_COLUMNS_SQL", text("SELECT coluna_que_nao_existe FROM nada")
    )
    assert await media_orphans.delete_upload_if_unreferenced(db_session, str(antiga)) is False
    assert antiga.exists() and apagados == []


async def test_sem_referencia_nenhuma_apaga_arquivo_e_respeita_o_mercado(
    db_session: AsyncSession, disco
):
    raiz, apagados = disco
    solta = _foto_antiga(raiz)
    assert await media_orphans.is_upload_referenced(db_session, str(solta)) is False
    # arquivo do BR com `market="EU"` nunca é apagado, mesmo sem referência
    assert await media_orphans.delete_upload_if_unreferenced(
        db_session, str(solta), market="EU"
    ) is False
    assert solta.exists()
    assert await media_orphans.delete_upload_if_unreferenced(
        db_session, str(solta), market="BR"
    ) is True
    assert not solta.exists()


async def test_identidade_do_arquivo():
    uid = str(uuid.uuid4())
    assert media_orphans.upload_identity(f"object://eu-products/{uid}.webp") == uid
    assert media_orphans.upload_identity(f"C:\\x\\uploads\\{uid.upper()}.png") == uid
    assert media_orphans.upload_identity("legado/foto-antiga-1.jpg") == "foto-antiga-1.jpg"
    assert media_orphans.upload_identity("a.jpg") is None
    assert media_orphans.upload_identity(None) is None
