import asyncio
import hashlib
import hmac
import io
import time
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from botocore.exceptions import ClientError
from fastapi import HTTPException
from PIL import Image
import pytest

from app.api.routers.media import get_media
from app.core import uploads
from app.core.config import settings


def _sample_png(size: tuple[int, int] = (1600, 1200)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#d7c4aa").save(output, format="PNG")
    return output.getvalue()


def test_thumbnail_webp_tem_dimensao_e_volume_reduzidos():
    original = _sample_png()

    thumbnail = uploads._make_thumbnail_bytes(original)

    assert len(thumbnail) < len(original)
    with Image.open(io.BytesIO(thumbnail)) as image:
        assert image.format == "WEBP"
        assert image.size == (320, 320)


def test_url_de_thumbnail_e_derivada_sem_alterar_referencia_original():
    reference = "object://products/abc-123.jpg"

    photo_url = uploads.build_photo_url(reference)
    thumbnail_url = uploads.build_thumbnail_url(reference)
    assert photo_url is not None and thumbnail_url is not None
    assert urlparse(photo_url).path == "/api/v1/media/products/abc-123.jpg"
    assert urlparse(thumbnail_url).path == "/api/v1/media/product-thumbnails/abc-123.jpg.webp"
    for url, key in (
        (photo_url, "products/abc-123.jpg"),
        (thumbnail_url, "product-thumbnails/abc-123.jpg.webp"),
    ):
        query = parse_qs(urlparse(url).query)
        expires = int(query["expires"][0])
        assert uploads.verify_media_signature(key, expires, query["signature"][0])


def test_assinatura_expirada_ou_adulterada_e_rejeitada():
    expires = int(time.time()) - 1
    signature = uploads._media_signature("products/foto.jpg", expires)

    assert not uploads.verify_media_signature("products/foto.jpg", expires, signature)
    assert not uploads.verify_media_signature(
        "products/outra.jpg",
        expires + 1000,
        signature,
    )


def test_assinatura_de_midia_usa_material_separado_da_jwt(monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_SIGNING_KEY", "")
    monkeypatch.setattr(settings, "MEDIA_SIGNING_KEY_PREVIOUS", "")
    key = "products/foto.jpg"
    expires = int(time.time()) + 60
    legacy = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"{key}\n{expires}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert uploads._media_signature(key, expires) != legacy
    assert not uploads.verify_media_signature(key, expires, legacy)


def test_rotacao_aceita_chave_anterior_durante_transicao(monkeypatch):
    current = "current-media-key-with-at-least-32-characters"
    previous = "previous-media-key-with-at-least-32-characters"
    monkeypatch.setattr(settings, "MEDIA_SIGNING_KEY", current)
    monkeypatch.setattr(settings, "MEDIA_SIGNING_KEY_PREVIOUS", previous)
    key = "products/foto.jpg"
    expires = int(time.time()) + 60
    old_signature = uploads._media_signature_with_key(
        key, expires, previous.encode("utf-8")
    )

    assert uploads.verify_media_signature(key, expires, old_signature)


def test_rota_de_midia_exige_assinatura_valida():
    async def run():
        expires = int(time.time()) + 60
        key = "products/foto.jpg"
        with patch(
            "app.api.routers.media.read_media_upload",
            AsyncMock(return_value=(b"image", "image/jpeg")),
        ) as reader:
            with pytest.raises(HTTPException) as exc:
                await get_media(key, expires, "invalida")
            assert exc.value.status_code == 403
            reader.assert_not_awaited()

            response = await get_media(
                key,
                expires,
                uploads._media_signature(key, expires),
            )
            assert response.body == b"image"
            assert response.headers["cache-control"].startswith("private")
            reader.assert_awaited_once_with(key)

    asyncio.run(run())


def test_imagem_legada_gera_thumbnail_sob_demanda(monkeypatch):
    original = _sample_png((800, 600))
    stored: dict[str, tuple[bytes, str]] = {
        "products/legacy.png": (original, "image/png")
    }

    class Body:
        def __init__(self, value: bytes):
            self.value = value

        def read(self) -> bytes:
            return self.value

    class Storage:
        def get_object(self, *, Bucket: str, Key: str):
            del Bucket
            if Key not in stored:
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey"}},
                    "GetObject",
                )
            content, content_type = stored[Key]
            return {"Body": Body(content), "ContentType": content_type}

        def put_object(
            self,
            *,
            Bucket: str,
            Key: str,
            Body: bytes,
            ContentType: str,
            CacheControl: str,
        ):
            del Bucket, CacheControl
            stored[Key] = (Body, ContentType)

    storage = Storage()
    monkeypatch.setattr(uploads, "_object_storage_client", lambda: storage)

    content, content_type = uploads._read_object_upload(
        "product-thumbnails/legacy.png.webp"
    )

    assert content_type == "image/webp"
    assert stored["product-thumbnails/legacy.png.webp"][0] == content
    with Image.open(io.BytesIO(content)) as image:
        assert image.size == (320, 320)
