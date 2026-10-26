"""P06 — fotos em MinIO real com buckets BR/EU distintos (ISO-32, REG-MEDIA).

Harness:

* PostgreSQL real pelo `db_session`/`client` do conftest de integração.
* MinIO do `docker-compose.test.yml`: buckets `ilya-br-test` e `ilya-eu-test`,
  cada um com usuário e política próprios. O endpoint vem de
  `TEST_OBJECT_STORAGE_ENDPOINT`; sem ele os testes que dependem do MinIO são
  pulados (não há fallback para storage em memória — o objetivo é o S3 real).
* A fixture `media_storage` aponta `settings.OBJECT_STORAGE_*` e
  `OBJECT_STORAGE_EU_*` para os buckets e limpa o `lru_cache` de
  `_object_storage_client`/`_eu_object_storage_client` no setup e no teardown,
  para nenhum cliente ligado ao MinIO sobreviver ao teste.

Propriedade e limpeza: o parser de `uploads.py` só aceita `<prefixo>/<uuid>.<ext>`
(sem prefixo de teste possível), então cada chave criada pela execução entra
numa lista de propriedade — a referência devolvida por `persist_upload`
(interceptada) ou a semeada pelo próprio teste — junto da miniatura derivada.
O teardown apaga só essas chaves exatas. Nunca lista o bucket, nunca compara
inventário antes/depois e nunca apaga bucket.

O SQL é revertido pelo rollback do harness, mas o storage não participa da
transação: por isso a limpeza explícita acima.
"""
import io
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import optionals as optionals_router
from app.api.routers import products as products_router
from app.core import uploads as uploads_module
from app.core.config import settings
from app.core.security import create_access_token
from app.models.market import VAT_PENDING, ProductMarket
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import make_product, make_product_market, make_user, make_user_market

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "images"
_REFERENCE_PREFIX = "object://"
_MEDIA_PATH_PREFIX = "/api/v1/media/"
# Únicas chaves que a limpeza aceita apagar: o formato exato gerado pelo app.
_OWNED_KEY = re.compile(
    r"^(?:eu-)?(?:products|optionals|product-thumbnails|optional-thumbnails|optional-variants)/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"\.(?:jpg|png|webp)(?:\.webp|\.v1-(?:thumb|gallery|zoom)\.webp)?$"
)
_DENIED_ROLES = ("cadastros", "executivo")


# ── Configuração do storage de teste ─────────────────────────────────────────


@dataclass(frozen=True)
class _MarketStorage:
    market: str
    endpoint: str
    bucket: str
    access_key_id: str
    secret_access_key: str


def _storage_from_env() -> tuple[_MarketStorage, _MarketStorage] | None:
    """Lê o MinIO de teste. Padrões = valores sintéticos do compose de teste."""
    endpoint = os.environ.get("TEST_OBJECT_STORAGE_ENDPOINT", "").strip()
    if not endpoint:
        return None
    env = os.environ.get
    br = _MarketStorage(
        market="BR",
        endpoint=endpoint,
        bucket=env("TEST_OBJECT_STORAGE_BR_BUCKET", "ilya-br-test"),
        access_key_id=env("TEST_OBJECT_STORAGE_BR_ACCESS_KEY_ID", "ilya-br-test-app"),
        secret_access_key=env(
            "TEST_OBJECT_STORAGE_BR_SECRET_ACCESS_KEY", "ilya-br-test-app-secret"
        ),
    )
    eu = _MarketStorage(
        market="EU",
        endpoint=env("TEST_OBJECT_STORAGE_EU_ENDPOINT", endpoint),
        bucket=env("TEST_OBJECT_STORAGE_EU_BUCKET", "ilya-eu-test"),
        access_key_id=env("TEST_OBJECT_STORAGE_EU_ACCESS_KEY_ID", "ilya-eu-test-app"),
        secret_access_key=env(
            "TEST_OBJECT_STORAGE_EU_SECRET_ACCESS_KEY", "ilya-eu-test-app-secret"
        ),
    )
    return br, eu


def _assert_distinct_test_buckets(br: _MarketStorage, eu: _MarketStorage) -> None:
    """ISO-32: BR e EU não podem apontar ao mesmo destino.

    Também recusa bucket sem `test` no nome — a limpeza nunca deve rodar
    contra bucket real por engano de variável de ambiente."""
    for storage in (br, eu):
        if not storage.bucket:
            raise AssertionError(f"Bucket {storage.market} de teste vazio.")
        if "test" not in storage.bucket.lower():
            raise AssertionError(
                f"Bucket {storage.market} {storage.bucket!r} não parece de teste."
            )
    br_target = (br.endpoint.rstrip("/").lower(), br.bucket)
    eu_target = (eu.endpoint.rstrip("/").lower(), eu.bucket)
    if br_target == eu_target:
        raise AssertionError(
            "Buckets BR e EU apontam ao mesmo destino; o isolamento de mídia "
            "por mercado não pode ser verificado."
        )


def _s3_client(storage: _MarketStorage):
    return boto3.client(
        "s3",
        endpoint_url=storage.endpoint,
        aws_access_key_id=storage.access_key_id,
        aws_secret_access_key=storage.secret_access_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _reset_app_storage_clients() -> None:
    """Fecha e descarta os clientes S3 cacheados pelo app (ambos lru_cache)."""
    for factory in (
        uploads_module._object_storage_client,
        uploads_module._eu_object_storage_client,
    ):
        if factory.cache_info().currsize:
            factory().close()
        factory.cache_clear()


def _market_of_key(key: str) -> str:
    return "EU" if key.startswith("eu-") else "BR"


def _error_code(exc: ClientError) -> str | None:
    return exc.response.get("Error", {}).get("Code")


class _MediaStorage:
    """Clientes de inspeção independentes do app + lista de propriedade."""

    def __init__(self, br: _MarketStorage, eu: _MarketStorage, monkeypatch):
        self.br = br
        self.eu = eu
        self._monkeypatch = monkeypatch
        self._inspectors = {"BR": _s3_client(br), "EU": _s3_client(eu)}
        self._buckets = {"BR": br.bucket, "EU": eu.bucket}
        self._owned: set[str] = set()
        # Toda referência devolvida por persist_upload durante o teste.
        self.app_references: list[str] = []

    # Propriedade

    def own_key(self, key: str) -> str:
        if not _OWNED_KEY.match(key):
            raise AssertionError(f"Chave fora do formato do app: {key!r}")
        self._owned.add(key)
        return key

    def own_reference(self, reference: str) -> str:
        if not reference.startswith(_REFERENCE_PREFIX):
            raise AssertionError(f"Upload não foi para o object storage: {reference!r}")
        key = self.own_key(reference.removeprefix(_REFERENCE_PREFIX))
        thumbnail_key = uploads_module._thumbnail_key_for_original(key)
        if thumbnail_key:
            self.own_key(thumbnail_key)
        return key

    def cleanup(self) -> None:
        errors = []
        try:
            for key in sorted(self._owned):
                market = _market_of_key(key)
                try:
                    self._inspectors[market].delete_object(
                        Bucket=self._buckets[market], Key=key
                    )
                except ClientError as exc:
                    errors.append(f"{key}: {_error_code(exc)}")
            self._owned.clear()
        finally:
            for inspector in self._inspectors.values():
                inspector.close()
        if errors:
            raise AssertionError(f"Falha ao limpar chaves do teste: {errors}")

    # Inspeção (cliente do mercado indicado, nunca o do app)

    def head(self, market: str, key: str) -> dict | None:
        try:
            return self._inspectors[market].head_object(
                Bucket=self._buckets[market], Key=key
            )
        except ClientError as exc:
            if _error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def head_foreign_bucket(self, market: str, key: str) -> None:
        """HEAD com a credencial de `market` no bucket do outro mercado."""
        foreign = self._buckets["EU" if market == "BR" else "BR"]
        self._inspectors[market].head_object(Bucket=foreign, Key=key)

    def read(self, market: str, key: str) -> bytes:
        return self._inspectors[market].get_object(
            Bucket=self._buckets[market], Key=key
        )["Body"].read()

    def seed_photo(self, market: str, content: bytes) -> str:
        """Grava original+miniatura como o app faria; devolve a referência."""
        prefix = "eu-products" if market == "EU" else "products"
        key = self.own_key(f"{prefix}/{uuid.uuid4()}.png")
        thumbnail_key = self.own_key(uploads_module._thumbnail_key_for_original(key))
        inspector, bucket = self._inspectors[market], self._buckets[market]
        inspector.put_object(Bucket=bucket, Key=key, Body=content, ContentType="image/png")
        inspector.put_object(
            Bucket=bucket,
            Key=thumbnail_key,
            Body=uploads_module._make_thumbnail_bytes(content),
            ContentType="image/webp",
        )
        return _REFERENCE_PREFIX + key

    def delete_owned(self, key: str) -> None:
        if key not in self._owned:
            raise AssertionError(f"Teste tentou apagar chave que não criou: {key!r}")
        market = _market_of_key(key)
        self._inspectors[market].delete_object(Bucket=self._buckets[market], Key=key)

    # Reconfiguração do app no meio do teste

    def reconfigure(self, **overrides) -> None:
        for name, value in overrides.items():
            self._monkeypatch.setattr(settings, name, value)
        _reset_app_storage_clients()


def _app_storage_settings(br: _MarketStorage, eu: _MarketStorage) -> dict:
    return {
        "OBJECT_STORAGE_ENDPOINT": br.endpoint,
        "OBJECT_STORAGE_ACCESS_KEY_ID": br.access_key_id,
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": br.secret_access_key,
        "OBJECT_STORAGE_BUCKET": br.bucket,
        "OBJECT_STORAGE_REGION": "us-east-1",
        "OBJECT_STORAGE_ADDRESSING_STYLE": "path",
        "OBJECT_STORAGE_EU_ENDPOINT": eu.endpoint,
        "OBJECT_STORAGE_EU_ACCESS_KEY_ID": eu.access_key_id,
        "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY": eu.secret_access_key,
        "OBJECT_STORAGE_EU_BUCKET": eu.bucket,
        "OBJECT_STORAGE_EU_REGION": "us-east-1",
        "OBJECT_STORAGE_EU_ADDRESSING_STYLE": "path",
        "REQUIRE_PERSISTENT_MEDIA_STORAGE": False,
    }


@pytest.fixture
def media_storage(monkeypatch):
    configured = _storage_from_env()
    if configured is None:
        pytest.skip(
            "TEST_OBJECT_STORAGE_ENDPOINT ausente; suba minio/minio-init do "
            "docker-compose.test.yml."
        )
    br, eu = configured
    _assert_distinct_test_buckets(br, eu)

    _reset_app_storage_clients()
    for name, value in _app_storage_settings(br, eu).items():
        monkeypatch.setattr(settings, name, value)
    _reset_app_storage_clients()

    harness = _MediaStorage(br, eu, monkeypatch)
    real_persist_upload = uploads_module.persist_upload

    async def recording_persist_upload(*args, **kwargs):
        reference = await real_persist_upload(*args, **kwargs)
        harness.app_references.append(reference)
        harness.own_reference(reference)
        return reference

    # Os routers importam o nome diretamente; copy_upload_to_market usa o do módulo.
    for module in (uploads_module, products_router, optionals_router):
        monkeypatch.setattr(module, "persist_upload", recording_persist_upload)
    try:
        yield harness
    finally:
        try:
            harness.cleanup()
        finally:
            _reset_app_storage_clients()


# ── Helpers de domínio ────────────────────────────────────────────────────────


async def _token(db: AsyncSession, market: str, role: str = "admin") -> str:
    user = await make_user(
        db,
        email=f"p06-{market.lower()}-{role}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole(role),
        home_market=market,
    )
    await make_user_market(db, user, market_code=market, role=role)
    return create_access_token(user.id, role, user.auth_version, market)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _product(
    db: AsyncSession,
    market: str,
    *,
    photo_path: str | None = None,
    shared_with_br: bool = False,
) -> Product:
    product = await make_product(db, market_code=market, description=f"P06 mídia {market}")
    await make_product_market(db, product)
    if shared_with_br:
        db.add(ProductMarket(
            product_id=product.id,
            market_code="BR",
            is_available=True,
            vat_rate=None,
            vat_status=VAT_PENDING,
            vat_source="import",
            approved_by_user_id=None,
            approved_at=None,
        ))
    if photo_path is not None:
        product.photo_path = photo_path
    await db.flush()
    return product


def _valid_png() -> bytes:
    return (_FIXTURES / "valid-small.png").read_bytes()


def _invalid_image() -> bytes:
    return (_FIXTURES / "invalid-image.txt").read_bytes()


def _other_png() -> bytes:
    """Segunda imagem sintética, diferente da fixture, para substituição."""
    output = io.BytesIO()
    Image.new("RGB", (64, 48), (180, 30, 30)).save(output, format="PNG")
    return output.getvalue()


def _oversized_png() -> bytes:
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    return _valid_png() + b"\0" * (limit + 1)


async def _upload(
    client: AsyncClient,
    token: str | None,
    product_id,
    *,
    content: bytes | None = None,
    filename: str = "foto.png",
    content_type: str = "image/png",
):
    return await client.post(
        f"/api/v1/products/{product_id}/upload-photo",
        files={"file": (filename, _valid_png() if content is None else content, content_type)},
        headers=_auth(token) if token else {},
    )


def _key_from_media_url(url: str) -> str:
    path = urlsplit(url).path
    assert path.startswith(_MEDIA_PATH_PREFIX), url
    return unquote(path.removeprefix(_MEDIA_PATH_PREFIX))


async def _photo_key(db: AsyncSession, product: Product) -> str | None:
    await db.refresh(product)
    if product.photo_path is None:
        return None
    assert product.photo_path.startswith(_REFERENCE_PREFIX), product.photo_path
    return product.photo_path.removeprefix(_REFERENCE_PREFIX)


def _thumbnail_key(key: str) -> str:
    thumbnail_key = uploads_module._thumbnail_key_for_original(key)
    assert thumbnail_key, key
    return thumbnail_key


def _other_market(market: str) -> str:
    return "EU" if market == "BR" else "BR"


# ── ISO-32: buckets distintos ─────────────────────────────────────────────────


async def test_iso32_guarda_falha_quando_br_e_eu_apontam_ao_mesmo_bucket():
    with pytest.raises(AssertionError, match="mesmo destino"):
        _assert_distinct_test_buckets(
            _MarketStorage("BR", "http://minio:9000", "ilya-shared-test", "k", "s"),
            _MarketStorage("EU", "http://MINIO:9000/", "ilya-shared-test", "k2", "s2"),
        )
    with pytest.raises(AssertionError, match="não parece de teste"):
        _assert_distinct_test_buckets(
            _MarketStorage("BR", "http://minio:9000", "ilya-producao", "k", "s"),
            _MarketStorage("EU", "http://minio:9000", "ilya-eu-test", "k", "s"),
        )
    _assert_distinct_test_buckets(
        _MarketStorage("BR", "http://minio:9000", "ilya-br-test", "k", "s"),
        _MarketStorage("EU", "http://minio:9000", "ilya-eu-test", "k", "s"),
    )


async def test_iso32_app_resolve_cada_prefixo_para_o_bucket_do_seu_mercado(media_storage):
    assert settings.OBJECT_STORAGE_BUCKET == media_storage.br.bucket
    assert settings.OBJECT_STORAGE_EU_BUCKET == media_storage.eu.bucket
    assert settings.OBJECT_STORAGE_BUCKET != settings.OBJECT_STORAGE_EU_BUCKET
    for key, expected in (
        ("products/x.png", media_storage.br.bucket),
        ("product-thumbnails/x.png.webp", media_storage.br.bucket),
        ("optionals/x.png", media_storage.br.bucket),
        ("eu-products/x.png", media_storage.eu.bucket),
        ("eu-product-thumbnails/x.png.webp", media_storage.eu.bucket),
        ("eu-optionals/x.png", media_storage.eu.bucket),
    ):
        assert uploads_module._storage_for_key(key)[1] == expected, key

    # Credenciais próprias: o usuário BR não alcança o bucket EU e vice-versa.
    probe = f"products/{uuid.uuid4()}.png"
    for market in ("BR", "EU"):
        with pytest.raises(ClientError) as denied:
            media_storage.head_foreign_bucket(market, probe)
        assert _error_code(denied.value) in {"403", "AccessDenied"}, market


# ── REG-MEDIA: upload, leitura, substituição, exclusão, thumbnail ────────────


@pytest.mark.parametrize(("market", "role", "prefix", "thumbnail_prefix"), [
    ("BR", "admin", "products/", "product-thumbnails/"),
    ("EU", "produtos", "eu-products/", "eu-product-thumbnails/"),
])
async def test_reg_media_upload_grava_original_e_thumbnail_so_no_bucket_do_mercado(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    market,
    role,
    prefix,
    thumbnail_prefix,
):
    token = await _token(db_session, market, role)
    product = await _product(db_session, market)

    response = await _upload(client, token, product.id)

    assert response.status_code == 200, response.text
    body = response.json()
    key = await _photo_key(db_session, product)
    assert media_storage.app_references == [_REFERENCE_PREFIX + key]
    assert key.startswith(prefix)
    thumbnail_key = _thumbnail_key(key)
    assert thumbnail_key.startswith(thumbnail_prefix)
    assert _key_from_media_url(body["photo_url"]) == key
    assert _key_from_media_url(body["thumbnail_url"]) == thumbnail_key

    original_head = media_storage.head(market, key)
    thumbnail_head = media_storage.head(market, thumbnail_key)
    assert original_head and original_head["ContentType"] == "image/png"
    assert thumbnail_head and thumbnail_head["ContentType"] == "image/webp"
    other = _other_market(market)
    assert media_storage.head(other, key) is None
    assert media_storage.head(other, thumbnail_key) is None

    original = await client.get(body["photo_url"])
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/png"
    assert original.headers["cache-control"].startswith("private")
    assert original.content == media_storage.read(market, key)
    with Image.open(io.BytesIO(original.content)) as image:
        assert image.format == "PNG"

    thumbnail = await client.get(body["thumbnail_url"])
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(thumbnail.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (320, 320)


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_reg_media_substituicao_remove_original_e_thumbnail_antigos(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    market,
):
    token = await _token(db_session, market, "vendedor")
    product = await _product(db_session, market)

    first = await _upload(client, token, product.id)
    assert first.status_code == 200, first.text
    old_key = await _photo_key(db_session, product)
    old_urls = (first.json()["photo_url"], first.json()["thumbnail_url"])

    second = await _upload(client, token, product.id, content=_other_png(), filename="nova.png")
    assert second.status_code == 200, second.text
    new_key = await _photo_key(db_session, product)

    assert new_key != old_key
    assert media_storage.head(market, new_key) is not None
    assert media_storage.head(market, _thumbnail_key(new_key)) is not None
    assert media_storage.head(market, old_key) is None
    assert media_storage.head(market, _thumbnail_key(old_key)) is None
    for url in old_urls:
        assert (await client.get(url)).status_code == 404
    replaced = await client.get(second.json()["photo_url"])
    assert replaced.status_code == 200
    with Image.open(io.BytesIO(replaced.content)) as image:
        assert image.size == (64, 48)


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_reg_media_exclusao_remove_objetos_e_referencia(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    market,
):
    token = await _token(db_session, market)
    product = await _product(db_session, market)
    uploaded = await _upload(client, token, product.id)
    assert uploaded.status_code == 200, uploaded.text
    key = await _photo_key(db_session, product)

    response = await client.delete(f"/api/v1/products/{product.id}/photo", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["photo_url"] is None
    assert response.json()["thumbnail_url"] is None
    assert await _photo_key(db_session, product) is None
    assert media_storage.head(market, key) is None
    assert media_storage.head(market, _thumbnail_key(key)) is None
    assert (await client.get(uploaded.json()["photo_url"])).status_code == 404


async def test_reg_media_thumbnail_ausente_e_regenerada_no_bucket_do_mercado(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    token = await _token(db_session, "EU")
    product = await _product(db_session, "EU")
    uploaded = await _upload(client, token, product.id)
    assert uploaded.status_code == 200, uploaded.text
    thumbnail_key = _thumbnail_key(await _photo_key(db_session, product))
    media_storage.delete_owned(thumbnail_key)
    assert media_storage.head("EU", thumbnail_key) is None

    response = await client.get(uploaded.json()["thumbnail_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert media_storage.head("EU", thumbnail_key) is not None
    assert media_storage.head("BR", thumbnail_key) is None


# ── ISO-32: URL adulterada, mercado cruzado, referência emprestada ───────────


async def test_iso32_url_adulterada_ou_expirada_retorna_403(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    token = await _token(db_session, "BR")
    product = await _product(db_session, "BR")
    uploaded = await _upload(client, token, product.id)
    assert uploaded.status_code == 200, uploaded.text
    key = await _photo_key(db_session, product)
    photo_url = uploaded.json()["photo_url"]
    query = parse_qs(urlsplit(photo_url).query)
    expires, signature = int(query["expires"][0]), query["signature"][0]
    tampered_signature = signature[:-1] + ("0" if signature[-1] != "0" else "1")
    past = int(time.time()) - 60

    def media_url(object_key: str, expires_at: int, sig: str) -> str:
        return f"{_MEDIA_PATH_PREFIX}{object_key}?" + urlencode(
            {"expires": expires_at, "signature": sig}
        )

    attempts = {
        "assinatura alterada": media_url(key, expires, tampered_signature),
        "chave EU com assinatura BR": media_url(f"eu-{key}", expires, signature),
        "miniatura com assinatura do original": media_url(_thumbnail_key(key), expires, signature),
        "expiração estendida": media_url(key, expires + 3600, signature),
        "expirada": media_url(key, past, uploads_module._media_signature(key, past)),
    }
    for label, url in attempts.items():
        response = await client.get(url)
        assert response.status_code == 403, label

    assert (await client.get(photo_url)).status_code == 200
    assert media_storage.head("BR", key) is not None


@pytest.mark.parametrize("action", ["substituir", "excluir"])
async def test_iso32_produto_eu_com_foto_br_emprestada_preserva_bucket_br(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    action,
):
    borrowed_reference = media_storage.seed_photo("BR", _valid_png())
    borrowed_key = borrowed_reference.removeprefix(_REFERENCE_PREFIX)
    product = await _product(db_session, "EU", photo_path=borrowed_reference)
    token = await _token(db_session, "EU")

    if action == "substituir":
        response = await _upload(client, token, product.id, content=_other_png())
    else:
        response = await client.delete(f"/api/v1/products/{product.id}/photo", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert media_storage.head("BR", borrowed_key) is not None
    assert media_storage.head("BR", _thumbnail_key(borrowed_key)) is not None
    new_key = await _photo_key(db_session, product)
    if action == "substituir":
        assert new_key.startswith("eu-products/")
        assert media_storage.head("EU", new_key) is not None
        assert media_storage.head("BR", new_key) is None
    else:
        assert new_key is None
        assert media_storage.app_references == []


async def test_iso32_mercado_cruzado_nao_alcanca_foto_do_outro_mercado(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    br_reference = media_storage.seed_photo("BR", _valid_png())
    br_product = await _product(db_session, "BR", photo_path=br_reference)
    eu_product = await _product(db_session, "EU")
    br_token = await _token(db_session, "BR")
    eu_token = await _token(db_session, "EU")

    eu_deletes_br = await client.delete(
        f"/api/v1/products/{br_product.id}/photo", headers=_auth(eu_token)
    )
    eu_uploads_br = await _upload(client, eu_token, br_product.id)
    br_uploads_eu = await _upload(client, br_token, eu_product.id)

    assert eu_deletes_br.status_code == 404
    assert eu_uploads_br.status_code == 404
    assert br_uploads_eu.status_code == 404
    assert media_storage.app_references == []
    await db_session.refresh(br_product)
    await db_session.refresh(eu_product)
    assert br_product.photo_path == br_reference
    assert eu_product.photo_path is None
    br_key = br_reference.removeprefix(_REFERENCE_PREFIX)
    assert media_storage.head("BR", br_key) is not None
    assert media_storage.head("BR", _thumbnail_key(br_key)) is not None


# ── Autorização e validação de arquivo ───────────────────────────────────────


async def test_reg_media_produto_eu_compartilhado_com_br_retorna_403_sem_objeto(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    product = await _product(db_session, "EU", shared_with_br=True)
    token = await _token(db_session, "EU")

    response = await _upload(client, token, product.id)

    assert response.status_code == 403
    assert "catálogo-base" in response.json()["detail"]
    assert media_storage.app_references == []
    assert await _photo_key(db_session, product) is None


@pytest.mark.parametrize("market", ["BR", "EU"])
@pytest.mark.parametrize("role", _DENIED_ROLES)
async def test_reg_media_papel_sem_permissao_nao_grava_nem_apaga(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    market,
    role,
):
    reference = media_storage.seed_photo(market, _valid_png())
    product = await _product(db_session, market, photo_path=reference)
    token = await _token(db_session, market, role)

    upload = await _upload(client, token, product.id)
    delete = await client.delete(f"/api/v1/products/{product.id}/photo", headers=_auth(token))
    anonymous_upload = await _upload(client, None, product.id)
    anonymous_delete = await client.delete(f"/api/v1/products/{product.id}/photo")

    assert upload.status_code == 403
    assert delete.status_code == 403
    assert anonymous_upload.status_code == 401
    assert anonymous_delete.status_code == 401
    assert media_storage.app_references == []
    await db_session.refresh(product)
    assert product.photo_path == reference
    key = reference.removeprefix(_REFERENCE_PREFIX)
    assert media_storage.head(market, key) is not None
    assert media_storage.head(market, _thumbnail_key(key)) is not None


@pytest.mark.parametrize(("label", "content", "filename", "status_code"), [
    ("texto com extensão png", _invalid_image, "falsa.png", 422),
    ("extensão não permitida", _valid_png, "foto.txt", 422),
    ("acima do limite", _oversized_png, "grande.png", 413),
])
@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_reg_media_arquivo_invalido_ou_grande_nao_cria_objeto(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
    market,
    label,
    content,
    filename,
    status_code,
):
    token = await _token(db_session, market)
    product = await _product(db_session, market)

    response = await _upload(client, token, product.id, content=content(), filename=filename)

    assert response.status_code == status_code, label
    assert media_storage.app_references == [], label
    assert await _photo_key(db_session, product) is None, label


# ── Falha de storage e EU sem bucket ─────────────────────────────────────────


async def test_reg_media_falha_de_storage_no_upload_preserva_foto_atual(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    from app.main import app

    current = media_storage.seed_photo("BR", _valid_png())
    product = await _product(db_session, "BR", photo_path=current)
    token = await _token(db_session, "BR")
    media_storage.reconfigure(OBJECT_STORAGE_SECRET_ACCESS_KEY="p06-credencial-invalida")

    # `client` já instalou o override de get_db_session; este cliente só
    # devolve o 500 em vez de propagar a exceção do app para o teste.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as failing_client:
        response = await _upload(failing_client, token, product.id, content=_other_png())

    assert response.status_code == 500
    assert media_storage.app_references == []
    await db_session.refresh(product)
    assert product.photo_path == current
    key = current.removeprefix(_REFERENCE_PREFIX)
    assert media_storage.head("BR", key) is not None
    assert media_storage.head("BR", _thumbnail_key(key)) is not None


async def test_reg_media_falha_de_storage_na_leitura_retorna_503(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    token = await _token(db_session, "BR")
    product = await _product(db_session, "BR")
    uploaded = await _upload(client, token, product.id)
    assert uploaded.status_code == 200, uploaded.text
    media_storage.reconfigure(OBJECT_STORAGE_SECRET_ACCESS_KEY="p06-credencial-invalida")

    response = await client.get(uploaded.json()["photo_url"])

    assert response.status_code == 503
    assert response.json()["detail"] == "Armazenamento de imagens temporariamente indisponível."


_EU_UNCONFIGURED = {
    "OBJECT_STORAGE_EU_ENDPOINT": "",
    "OBJECT_STORAGE_EU_ACCESS_KEY_ID": "",
    "OBJECT_STORAGE_EU_SECRET_ACCESS_KEY": "",
    "OBJECT_STORAGE_EU_BUCKET": "",
}


async def test_reg_media_eu_sem_bucket_retorna_503_sem_fallback_br(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    media_storage.reconfigure(**_EU_UNCONFIGURED)
    assert settings.object_storage_configured()
    assert not settings.eu_object_storage_configured()
    product = await _product(db_session, "EU")
    token = await _token(db_session, "EU")

    response = await _upload(client, token, product.id)

    assert response.status_code == 503
    assert response.json()["detail"] == "Armazenamento de fotos do mercado europeu não configurado."
    assert media_storage.app_references == []
    assert await _photo_key(db_session, product) is None


async def test_reg_media_foto_eu_nao_e_servida_do_bucket_br_sem_bucket_eu(
    client: AsyncClient,
    db_session: AsyncSession,
    media_storage,
):
    token = await _token(db_session, "EU")
    product = await _product(db_session, "EU")
    uploaded = await _upload(client, token, product.id)
    assert uploaded.status_code == 200, uploaded.text
    key = await _photo_key(db_session, product)
    media_storage.reconfigure(**_EU_UNCONFIGURED)

    response = await client.get(uploaded.json()["photo_url"])

    assert response.status_code == 404
    assert media_storage.head("BR", key) is None
    assert media_storage.head("EU", key) is not None
