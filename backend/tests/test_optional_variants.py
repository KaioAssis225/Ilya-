"""Variantes de apresentação dos opcionais (miniatura 160, galeria 480, zoom 960).

Garantias travadas aqui:

- encaixe proporcional: nada é recortado, distorcido nem ampliado;
- orientação EXIF corrigida e transparência preservada;
- chaves versionadas, no mesmo bucket/prefixo de mercado da original;
- upload de opcional grava as variantes; foto de móvel não ganha variantes;
- variante ausente (acervo legado) é gerada na leitura a partir da original;
- exclusão remove as variantes junto com a original.
"""

import asyncio
import io
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError
from PIL import Image

from app.core import uploads
from app.core.config import settings


def _image_bytes(size, *, mode="RGB", color="#8a6f52", fmt="PNG", exif_orientation=None) -> bytes:
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(output, format="JPEG", exif=exif)
    else:
        image.save(output, format=fmt)
    return output.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "WEBP"
        return image.size


@pytest.mark.parametrize("variant, expected", [
    ("thumb", (160, 80)),
    ("gallery", (480, 240)),
    ("zoom", (960, 480)),
])
def test_variante_preserva_proporcao_sem_preencher(variant, expected):
    data = uploads._make_variant_bytes(_image_bytes((2000, 1000)), variant)
    assert _size(data) == expected


def test_fonte_pequena_nao_e_ampliada():
    source = _image_bytes((378, 378))
    for variant in uploads.OPTIONAL_VARIANTS:
        assert _size(uploads._make_variant_bytes(source, variant))[0] <= 378
    assert _size(uploads._make_variant_bytes(source, "zoom")) == (378, 378)


def test_orientacao_exif_e_aplicada():
    # Orientação 6 = girar 90°: o arquivo 400x200 é exibido como 200x400.
    source = _image_bytes((400, 200), exif_orientation=6)
    assert _size(uploads._make_variant_bytes(source, "zoom")) == (200, 400)


def test_transparencia_preservada():
    source = _image_bytes((300, 300), mode="RGBA", color=(10, 20, 30, 0))
    with Image.open(io.BytesIO(uploads._make_variant_bytes(source, "gallery"))) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((5, 5))[3] == 0


def test_perfil_icc_invalido_nao_quebra_a_variante():
    image = Image.new("RGB", (300, 200), "#335577")
    output = io.BytesIO()
    image.save(output, format="PNG", icc_profile=b"nao-e-um-perfil")
    assert _size(uploads._make_variant_bytes(output.getvalue(), "gallery")) == (300, 200)


def test_cmyk_vira_rgb_e_perfil_valido_e_aplicado():
    from PIL import ImageCms

    cmyk = io.BytesIO()
    Image.new("CMYK", (120, 60), (0, 0, 0, 0)).save(cmyk, format="JPEG")
    with Image.open(io.BytesIO(uploads._make_variant_bytes(cmyk.getvalue(), "zoom"))) as image:
        assert image.mode == "RGB" and image.size == (120, 60)
        assert min(image.getpixel((10, 10))) > 240  # CMYK sem tinta = branco

    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    rgb = io.BytesIO()
    Image.new("RGB", (100, 100), (200, 50, 50)).save(rgb, format="PNG", icc_profile=srgb)
    with Image.open(io.BytesIO(uploads._make_variant_bytes(rgb.getvalue(), "gallery"))) as image:
        red, green, blue = image.getpixel((50, 50))
        assert abs(red - 200) <= 6 and abs(green - 50) <= 6 and abs(blue - 50) <= 6


def test_chaves_versionadas_por_mercado():
    assert uploads._optional_variant_key("optionals/a.jpg", "gallery") == (
        f"optional-variants/a.jpg.{uploads.OPTIONAL_VARIANT_VERSION}-gallery.webp"
    )
    eu_key = uploads._optional_variant_key("eu-optionals/a.jpg", "zoom")
    assert eu_key.startswith("eu-optional-variants/")
    assert uploads._is_eu_key(eu_key)
    assert uploads._optional_variant_key("products/a.jpg", "zoom") is None
    assert uploads._optional_variant_key("optionals/a.jpg", "gigante") is None
    assert uploads._original_key_for_variant(eu_key) == ("eu-optionals/a.jpg", "zoom")
    assert uploads._original_key_for_variant("optional-variants/a.jpg.v0-zoom.webp") is None
    assert uploads._original_key_for_variant("optional-variants/x/a.jpg.v1-zoom.webp") is None


def test_urls_das_variantes_sao_assinadas():
    variants = uploads.build_optional_variants("object://optionals/abc.jpg")
    assert set(variants) == {"thumb", "gallery", "zoom"}
    assert variants["gallery"]["max_side"] == 480
    url = urlparse(variants["zoom"]["url"])
    key = url.path.removeprefix("/api/v1/media/")
    query = parse_qs(url.query)
    assert uploads.verify_media_signature(key, int(query["expires"][0]), query["signature"][0])
    assert uploads.build_optional_variants(None) is None
    assert uploads.build_optional_variants("object://products/abc.jpg") is None


class FakeBucket:
    def __init__(self, name):
        self.name = name
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(self, *, Bucket, Key, Body, **_):
        assert Bucket == self.name
        self.objects[Key] = Body

    def delete_object(self, *, Bucket, Key):
        assert Bucket == self.name
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def head_object(self, *, Bucket, Key):
        assert Bucket == self.name
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def get_object(self, *, Bucket, Key):
        assert Bucket == self.name
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
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
    monkeypatch.setattr(uploads, "_object_storage_client", lambda: br)
    monkeypatch.setattr(uploads, "_eu_object_storage_client", lambda: eu)
    return br, eu


def test_upload_de_opcional_eu_grava_variantes_no_bucket_europeu(buckets):
    br, eu = buckets
    ref = asyncio.run(uploads.persist_upload(
        _image_bytes((1400, 700)), f"{settings.UPLOAD_DIR}/optionals", "png", market="EU",
    ))
    key = ref.removeprefix("object://")
    expected = {key, uploads._thumbnail_key_for_original(key)} | {
        uploads._optional_variant_key(key, variant) for variant in uploads.OPTIONAL_VARIANTS
    }
    assert set(eu.objects) == expected
    assert br.objects == {}
    assert _size(eu.objects[uploads._optional_variant_key(key, "zoom")]) == (960, 480)


def test_upload_de_produto_nao_ganha_variantes(buckets):
    br, _ = buckets
    ref = asyncio.run(uploads.persist_upload(_image_bytes((800, 800)), settings.UPLOAD_DIR, "png"))
    key = ref.removeprefix("object://")
    assert set(br.objects) == {key, uploads._thumbnail_key_for_original(key)}


def test_variante_legada_e_gerada_na_leitura(buckets):
    br, _ = buckets
    br.objects["optionals/legado.png"] = _image_bytes((1000, 500))
    variant_key = uploads._optional_variant_key("optionals/legado.png", "gallery")
    content, content_type = asyncio.run(uploads.read_object_upload(variant_key))
    assert content_type == "image/webp"
    assert _size(content) == (480, 240)
    assert variant_key in br.objects  # cache gravado


def test_variante_sem_original_e_404(buckets):
    variant_key = uploads._optional_variant_key("optionals/sumiu.png", "thumb")
    with pytest.raises(FileNotFoundError):
        asyncio.run(uploads.read_object_upload(variant_key))


def test_exclusao_remove_variantes(buckets):
    br, _ = buckets
    ref = asyncio.run(uploads.persist_upload(
        _image_bytes((600, 600)), f"{settings.UPLOAD_DIR}/optionals", "png",
    ))
    asyncio.run(uploads.delete_upload(ref))
    assert br.objects == {}


def test_variante_local_legada_gerada_e_restrita_a_optionals(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    optionals_dir = tmp_path / "optionals"
    optionals_dir.mkdir()
    (optionals_dir / "a.png").write_bytes(_image_bytes((900, 300)))
    variant_path = uploads._local_variant_path(str(optionals_dir / "a.png"), "thumb")
    local_key = uploads._local_key_from_path(variant_path)
    content, content_type = asyncio.run(uploads.read_media_upload(local_key))
    assert content_type == "image/webp"
    assert _size(content) == (160, 53)

    (tmp_path / "b.png").write_bytes(_image_bytes((900, 300)))
    outside = uploads._local_key_from_path(
        uploads._local_variant_path(str(tmp_path / "b.png"), "thumb")
    )
    with pytest.raises(FileNotFoundError):
        asyncio.run(uploads.read_media_upload(outside))


def test_tamanho_maximo_da_fonte_para_aviso():
    assert uploads.image_max_side(_image_bytes((378, 300))) == 378
    assert uploads.image_max_side(b"lixo") is None


def test_inventario_simula_sem_gravar_e_aplica_so_o_que_falta(buckets):
    br, _ = buckets
    original = "optionals/legado.png"
    br.objects[original] = _image_bytes((378, 378))
    zoom_key = uploads._optional_variant_key(original, "zoom")
    br.objects[zoom_key] = b"ja-existe"

    simulated = asyncio.run(uploads.inspect_optional_variants(f"object://{original}", apply=False))
    assert simulated["missing"] == ["thumb", "gallery"]
    assert simulated["generated"] == []
    assert simulated["max_side"] == 378 and simulated["low_resolution"] is True
    assert len(simulated["sha256"]) == 64
    assert set(br.objects) == {original, zoom_key}

    applied = asyncio.run(uploads.inspect_optional_variants(f"object://{original}", apply=True))
    assert applied["generated"] == ["thumb", "gallery"] and applied["missing"] == []
    assert br.objects[zoom_key] == b"ja-existe"  # não sobrescreve

    again = asyncio.run(uploads.inspect_optional_variants(f"object://{original}", apply=True))
    assert again["generated"] == [] and again["missing"] == []


def test_inventario_recusa_referencia_de_produto(buckets):
    br, _ = buckets
    br.objects["products/a.png"] = _image_bytes((50, 50))
    with pytest.raises(ValueError):
        asyncio.run(uploads.inspect_optional_variants("object://products/a.png", apply=True))
