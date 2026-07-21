import io

from botocore.exceptions import ClientError
from PIL import Image

from app.core import uploads


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

    assert uploads.build_photo_url(reference) == "/api/v1/media/products/abc-123.jpg"
    assert uploads.build_thumbnail_url(reference) == (
        "/api/v1/media/product-thumbnails/abc-123.jpg.webp"
    )


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
