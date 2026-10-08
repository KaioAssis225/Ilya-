"""Fotos do mercado europeu em bucket próprio.

O prefixo da chave (`eu-*`) decide o bucket. As garantias travadas aqui:

- upload EU vai para o bucket europeu, nunca para o brasileiro;
- sem bucket europeu configurado, upload EU é recusado em vez de cair no BR;
- produto/opcional EU que ainda empresta a foto do BR não apaga o arquivo
  brasileiro ao trocar ou excluir a foto;
- a sincronização copia sem tocar a origem.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.routers import markets as markets_module
from app.core import uploads as uploads_module
from app.core.config import settings


class FakeBucket:
    def __init__(self, name: str):
        self.name = name
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(self, *, Bucket, Key, Body, **_):
        assert Bucket == self.name, f"gravou no bucket errado: {Bucket}"
        self.objects[Key] = Body

    def delete_object(self, *, Bucket, Key):
        assert Bucket == self.name, f"apagou no bucket errado: {Bucket}"
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def get_object(self, *, Bucket, Key):
        assert Bucket == self.name, f"leu no bucket errado: {Bucket}"
        return {"Body": SimpleNamespace(read=lambda: self.objects[Key]), "ContentType": "image/png"}


@pytest.fixture
def buckets(monkeypatch):
    br, eu = FakeBucket("br-uploads"), FakeBucket("eu-uploads")
    for name, value in {
        "OBJECT_STORAGE_ENDPOINT": "https://storage.example",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "br-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "br-secret",
        "OBJECT_STORAGE_BUCKET": br.name,
        "OBJECT_STORAGE_EU_ENDPOINT": "https://storage.example",
        "OBJECT_STORAGE_EU_ACCESS_KEY_ID": "eu-key",
        "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY": "eu-secret",
        "OBJECT_STORAGE_EU_BUCKET": eu.name,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(uploads_module, "_object_storage_client", lambda: br)
    monkeypatch.setattr(uploads_module, "_eu_object_storage_client", lambda: eu)
    monkeypatch.setattr(uploads_module, "_make_thumbnail_bytes", lambda _: b"mini")
    return br, eu


def test_upload_eu_vai_para_o_bucket_europeu(buckets):
    br, eu = buckets
    ref = asyncio.run(uploads_module.persist_upload(
        b"foto", settings.UPLOAD_DIR, "png", market="EU"
    ))
    key = ref.removeprefix("object://")
    assert key.startswith("eu-products/")
    assert set(eu.objects) == {key, uploads_module._thumbnail_key_for_original(key)}
    assert br.objects == {}


def test_upload_de_opcional_eu_usa_prefixo_proprio(buckets):
    _, eu = buckets
    ref = asyncio.run(uploads_module.persist_upload(
        b"foto", f"{settings.UPLOAD_DIR}/optionals", "webp", market="EU"
    ))
    assert ref.startswith("object://eu-optionals/")
    assert any(k.startswith("eu-optional-thumbnails/") for k in eu.objects)


def test_upload_br_continua_no_bucket_brasileiro(buckets):
    br, eu = buckets
    ref = asyncio.run(uploads_module.persist_upload(b"foto", settings.UPLOAD_DIR, "png"))
    assert ref.startswith("object://products/")
    assert len(br.objects) == 2 and eu.objects == {}


def test_sem_bucket_europeu_o_upload_eu_e_recusado(buckets, monkeypatch):
    br, _ = buckets
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", "")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads_module.persist_upload(
            b"foto", settings.UPLOAD_DIR, "png", market="EU"
        ))
    assert exc.value.status_code == 503
    # Recusar é o ponto: cair no bucket BR desfaria a separação em silêncio.
    assert br.objects == {}


def test_railway_sem_bucket_br_recusa_disco_efemero(monkeypatch):
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-test")
    monkeypatch.setattr(settings, "DEBUG", False)
    for name in (
        "OBJECT_STORAGE_ENDPOINT",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "OBJECT_STORAGE_BUCKET",
    ):
        monkeypatch.setattr(settings, name, "")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads_module.persist_upload(
            b"foto", settings.UPLOAD_DIR, "png", market="BR"
        ))

    assert exc.value.status_code == 503
    assert "persistente" in exc.value.detail


def test_foto_emprestada_do_br_nao_e_apagada_pelo_mercado_eu(buckets):
    br, _ = buckets
    br.objects["products/origem.png"] = b"foto-br"
    asyncio.run(uploads_module.delete_upload("object://products/origem.png", market="EU"))
    assert br.deleted == []
    assert "products/origem.png" in br.objects


def test_foto_propria_do_eu_e_apagada_no_bucket_europeu(buckets):
    br, eu = buckets
    eu.objects["eu-products/x.png"] = b"foto-eu"
    asyncio.run(uploads_module.delete_upload("object://eu-products/x.png", market="EU"))
    assert "eu-products/x.png" in eu.deleted
    assert br.deleted == []


def test_leitura_de_chave_europeia_vem_do_bucket_europeu(buckets):
    _, eu = buckets
    eu.objects["eu-products/x.png"] = b"foto-eu"
    content, _ = asyncio.run(uploads_module.read_object_upload("eu-products/x.png"))
    assert content == b"foto-eu"


def test_chave_europeia_sem_bucket_europeu_nao_e_servida(buckets, monkeypatch):
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", "")
    with pytest.raises(FileNotFoundError):
        asyncio.run(uploads_module.read_object_upload("eu-products/x.png"))


def test_copia_para_o_eu_preserva_a_origem(buckets):
    br, eu = buckets
    br.objects["products/origem.png"] = b"foto-br"
    nova = asyncio.run(uploads_module.copy_upload_to_market(
        "object://products/origem.png", kind="products"
    ))
    key = nova.removeprefix("object://")
    assert key.startswith("eu-products/")
    assert eu.objects[key] == b"foto-br"
    assert br.objects["products/origem.png"] == b"foto-br"
    assert br.deleted == []


def _scalars(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _count(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def test_sincronizacao_copia_e_troca_a_referencia(buckets, monkeypatch):
    produto = SimpleNamespace(
        id=uuid.uuid4(), product_code="IAC0120",
        photo_path="object://products/a.png",
    )
    opcional = SimpleNamespace(
        id=uuid.uuid4(), color_name="AREIA",
        photo_path="object://optionals/b.png",
    )
    copiados = []

    async def fake_copy(path, *, kind):
        copiados.append((path, kind))
        return f"object://eu-{kind}/novo.png"

    monkeypatch.setattr(markets_module, "copy_upload_to_market", fake_copy)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _scalars([produto]), _scalars([opcional]), _count(0), _count(0),
    ])
    db.commit = AsyncMock()

    resposta = asyncio.run(markets_module.sync_europe_media(limit=20, db=db, _=None))

    assert resposta == {"copied": 2, "failed": [], "remaining": 0}
    assert copiados == [
        ("object://products/a.png", "products"),
        ("object://optionals/b.png", "optionals"),
    ]
    assert produto.photo_path == "object://eu-products/novo.png"
    assert opcional.photo_path == "object://eu-optionals/novo.png"
    assert db.commit.await_count == 2


def test_falha_de_um_arquivo_nao_interrompe_o_lote(buckets, monkeypatch):
    quebrado = SimpleNamespace(id=uuid.uuid4(), product_code="X1", photo_path="object://products/x.png")
    bom = SimpleNamespace(id=uuid.uuid4(), product_code="X2", photo_path="object://products/y.png")

    async def fake_copy(path, *, kind):
        if path.endswith("x.png"):
            raise FileNotFoundError(path)
        return "object://eu-products/y2.png"

    monkeypatch.setattr(markets_module, "copy_upload_to_market", fake_copy)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _scalars([quebrado, bom]), _scalars([]), _count(1), _count(0),
    ])
    db.commit = AsyncMock()

    resposta = asyncio.run(markets_module.sync_europe_media(limit=20, db=db, _=None))

    assert resposta["copied"] == 1
    assert resposta["remaining"] == 1
    assert resposta["failed"][0]["code"] == "X1"
    assert quebrado.photo_path == "object://products/x.png"


def test_sincronizacao_exige_bucket_europeu(monkeypatch):
    monkeypatch.setattr(settings, "OBJECT_STORAGE_EU_BUCKET", "")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(markets_module.sync_europe_media(limit=20, db=MagicMock(), _=None))
    assert exc.value.status_code == 409
