import asyncio
import hashlib
import hmac
import io
import logging
import mimetypes
import os
import tempfile
import time
import uuid
import warnings
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    IncompleteReadError,
    ResponseStreamingError,
)
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings


logger = logging.getLogger("ilya.uploads")

_CHUNK_SIZE = 64 * 1024
_FORMAT_TO_EXTENSION = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_IMAGE_PROCESSING_SEMAPHORE = asyncio.Semaphore(2)
# Uma página de catálogo pede dezenas de fotos de uma vez. Sem teto, cada uma
# ocupa uma thread e uma conexão com o bucket; acima do pool do urllib3 as
# conexões são descartadas e a leitura do corpo cai no meio (503 em rajada).
# O teto de leituras fica abaixo do pool para nunca disputar conexão.
_STORAGE_MAX_POOL_CONNECTIONS = 32
_MEDIA_READ_SEMAPHORE = asyncio.Semaphore(16)
# O retry do botocore cobre a requisição, não a leitura do corpo: uma conexão
# que cai no meio do download só se recupera pedindo o objeto de novo.
_STORAGE_READ_ATTEMPTS = 3
_STORAGE_STREAM_ERRORS = (ResponseStreamingError, IncompleteReadError)
_OBJECT_REFERENCE_PREFIX = "object://"
# O prefixo da chave decide o bucket: `eu-*` mora no bucket europeu, o resto no
# principal. A chave já é assinada na URL de mídia, então o roteamento não
# depende de nada que o cliente controle, e o banco não precisa de coluna nova.
_EU_ORIGINAL_PREFIXES = {"eu-products", "eu-optionals"}
_ORIGINAL_OBJECT_KEY_PREFIXES = {"products", "optionals"} | _EU_ORIGINAL_PREFIXES
_THUMBNAIL_PREFIX_BY_ORIGINAL = {
    "products": "product-thumbnails",
    "optionals": "optional-thumbnails",
    "eu-products": "eu-product-thumbnails",
    "eu-optionals": "eu-optional-thumbnails",
}
# Variantes de apresentação só existem para opcionais (amostras de material).
# Fotos de móveis seguem só com a miniatura acima. A versão entra na chave:
# mudar a política gera chaves novas em vez de sobrescrever arquivos imutáveis.
OPTIONAL_VARIANT_VERSION = "v1"
# nome -> (maior lado máximo, qualidade WebP). Fontes menores não são ampliadas.
OPTIONAL_VARIANTS: dict[str, tuple[int, int]] = {
    "thumb": (160, 82),
    "gallery": (480, 84),
    "zoom": (960, 88),
}
_VARIANT_PREFIX_BY_ORIGINAL = {
    "optionals": "optional-variants",
    "eu-optionals": "eu-optional-variants",
}
_ORIGINAL_PREFIX_BY_VARIANT = {
    variant: original for original, variant in _VARIANT_PREFIX_BY_ORIGINAL.items()
}
_LOCAL_VARIANT_DIRECTORY = "variants"
# Abaixo disso a foto é aceita, mas sinalizada para substituição futura.
OPTIONAL_RECOMMENDED_MIN_SIDE = 1200
_EU_KEY_PREFIXES = _EU_ORIGINAL_PREFIXES | {
    _THUMBNAIL_PREFIX_BY_ORIGINAL[prefix] for prefix in _EU_ORIGINAL_PREFIXES
} | {"eu-optional-variants"}
_ORIGINAL_PREFIX_BY_THUMBNAIL = {
    thumbnail: original
    for original, thumbnail in _THUMBNAIL_PREFIX_BY_ORIGINAL.items()
}
_OBJECT_KEY_PREFIXES = (
    _ORIGINAL_OBJECT_KEY_PREFIXES
    | set(_ORIGINAL_PREFIX_BY_THUMBNAIL)
    | set(_ORIGINAL_PREFIX_BY_VARIANT)
)
_THUMBNAIL_DIMENSION = 320
_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _derived_media_signing_key() -> bytes:
    """Separa criptograficamente mídia e JWT no ambiente local/teste."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b"ilya-media-url-signing-v1",
        hashlib.sha256,
    ).digest()


def _current_media_signing_key() -> bytes:
    if settings.MEDIA_SIGNING_KEY:
        return settings.MEDIA_SIGNING_KEY.encode("utf-8")
    return _derived_media_signing_key()


def _media_signature_with_key(object_key: str, expires: int, key: bytes) -> str:
    payload = f"{object_key}\n{expires}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _media_signature(object_key: str, expires: int) -> str:
    return _media_signature_with_key(
        object_key,
        expires,
        _current_media_signing_key(),
    )


def verify_media_signature(
    object_key: str,
    expires: int,
    signature: str,
    *,
    now: int | None = None,
) -> bool:
    current = int(time.time()) if now is None else now
    if expires < current or not signature:
        return False
    keys = [_current_media_signing_key()]
    if settings.MEDIA_SIGNING_KEY_PREVIOUS:
        keys.append(settings.MEDIA_SIGNING_KEY_PREVIOUS.encode("utf-8"))
    return any(
        hmac.compare_digest(
            _media_signature_with_key(object_key, expires, key),
            signature,
        )
        for key in keys
    )


def _media_url_expires(current: int) -> int:
    """Fim da validade arredondado para uma janela do tamanho do TTL.

    Com `now + TTL` cada resposta da API gerava outra URL para a mesma foto e
    o navegador nunca reaproveitava o cache. Arredondando, a URL fica igual
    durante a janela; a validade passa a ficar entre 1x e 2x o TTL."""
    window = max(1, settings.MEDIA_URL_TTL_SECONDS)
    return (current // window + 1) * window + settings.MEDIA_URL_TTL_SECONDS


def _signed_media_url(object_key: str, *, now: int | None = None) -> str:
    current = int(time.time()) if now is None else now
    expires = _media_url_expires(current)
    query = urlencode({
        "expires": expires,
        "signature": _media_signature(object_key, expires),
    })
    return f"/api/v1/media/{quote(object_key, safe='/')}?{query}"


def _local_key_from_path(photo_path: str) -> str | None:
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    candidate = Path(photo_path).resolve()
    try:
        relative = candidate.relative_to(upload_root)
    except ValueError:
        return None
    return "local/" + relative.as_posix()


def _normalized_addressing_style(style: str) -> str:
    return "virtual" if style == "virtual-host" else style


def _storage_client_config(addressing_style: str) -> Config:
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": _normalized_addressing_style(addressing_style)},
        max_pool_connections=_STORAGE_MAX_POOL_CONNECTIONS,
        retries={"mode": "standard", "max_attempts": 4},
        connect_timeout=5,
        read_timeout=20,
        tcp_keepalive=True,
    )


@lru_cache(maxsize=1)
def _object_storage_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
        aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        region_name=settings.OBJECT_STORAGE_REGION,
        config=_storage_client_config(settings.OBJECT_STORAGE_ADDRESSING_STYLE),
    )


@lru_cache(maxsize=1)
def _eu_object_storage_client():
    style = (
        settings.OBJECT_STORAGE_EU_ADDRESSING_STYLE
        or settings.OBJECT_STORAGE_ADDRESSING_STYLE
    )
    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORAGE_EU_ENDPOINT,
        aws_access_key_id=settings.OBJECT_STORAGE_EU_ACCESS_KEY_ID,
        aws_secret_access_key=settings.OBJECT_STORAGE_EU_SECRET_ACCESS_KEY,
        region_name=settings.OBJECT_STORAGE_EU_REGION,
        config=_storage_client_config(style),
    )


def _is_eu_key(object_key: str) -> bool:
    return object_key.partition("/")[0] in _EU_KEY_PREFIXES


def _storage_configured_for_key(object_key: str) -> bool:
    if _is_eu_key(object_key):
        return settings.eu_object_storage_configured()
    return settings.object_storage_configured()


def _storage_for_key(object_key: str):
    """Cliente e bucket donos da chave. Nunca cai de um bucket para o outro:
    chave europeia sem bucket europeu configurado é erro, não fallback."""
    if _is_eu_key(object_key):
        return _eu_object_storage_client(), settings.OBJECT_STORAGE_EU_BUCKET
    return _object_storage_client(), settings.OBJECT_STORAGE_BUCKET


def _object_key_from_reference(reference: str | None) -> str | None:
    if not reference or not reference.startswith(_OBJECT_REFERENCE_PREFIX):
        return None
    key = reference[len(_OBJECT_REFERENCE_PREFIX):]
    prefix, separator, filename = key.partition("/")
    if (
        separator != "/"
        or prefix not in _ORIGINAL_OBJECT_KEY_PREFIXES
        or not filename
        or "/" in filename
    ):
        return None
    return key


def build_photo_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    object_key = _object_key_from_reference(photo_path)
    if object_key:
        return _signed_media_url(object_key)
    local_key = _local_key_from_path(photo_path)
    return _signed_media_url(local_key) if local_key else None


def _thumbnail_key_for_original(object_key: str) -> str | None:
    prefix, separator, filename = object_key.partition("/")
    thumbnail_prefix = _THUMBNAIL_PREFIX_BY_ORIGINAL.get(prefix)
    if not separator or not thumbnail_prefix or not filename or "/" in filename:
        return None
    return f"{thumbnail_prefix}/{filename}.webp"


def _original_key_for_thumbnail(thumbnail_key: str) -> str | None:
    prefix, separator, filename = thumbnail_key.partition("/")
    original_prefix = _ORIGINAL_PREFIX_BY_THUMBNAIL.get(prefix)
    if (
        not separator
        or not original_prefix
        or not filename.endswith(".webp")
        or "/" in filename
    ):
        return None
    return f"{original_prefix}/{filename[:-5]}"


def _local_thumbnail_path(photo_path: str) -> str:
    return os.path.join(
        os.path.dirname(photo_path),
        "thumbnails",
        os.path.basename(photo_path) + ".webp",
    )


def build_thumbnail_url(photo_path: str | None) -> str | None:
    """Retorna miniatura persistente; imagens legadas são geradas sob demanda."""
    if not photo_path:
        return None
    object_key = _object_key_from_reference(photo_path)
    if object_key:
        thumbnail_key = _thumbnail_key_for_original(object_key)
        if thumbnail_key:
            return _signed_media_url(thumbnail_key)
    thumbnail_path = _local_thumbnail_path(photo_path)
    if os.path.isfile(thumbnail_path):
        return build_photo_url(thumbnail_path)
    return build_photo_url(photo_path)


def _optional_variant_key(object_key: str, variant: str) -> str | None:
    prefix, separator, filename = object_key.partition("/")
    variant_prefix = _VARIANT_PREFIX_BY_ORIGINAL.get(prefix)
    if (
        not separator
        or not variant_prefix
        or not filename
        or "/" in filename
        or variant not in OPTIONAL_VARIANTS
    ):
        return None
    return f"{variant_prefix}/{filename}.{OPTIONAL_VARIANT_VERSION}-{variant}.webp"


def _variant_from_filename(filename: str) -> tuple[str, str] | None:
    """`<original>.v1-gallery.webp` -> (`<original>`, `gallery`)."""
    for variant in OPTIONAL_VARIANTS:
        suffix = f".{OPTIONAL_VARIANT_VERSION}-{variant}.webp"
        if filename.endswith(suffix) and len(filename) > len(suffix):
            return filename[: -len(suffix)], variant
    return None


def _original_key_for_variant(variant_key: str) -> tuple[str, str] | None:
    prefix, separator, filename = variant_key.partition("/")
    original_prefix = _ORIGINAL_PREFIX_BY_VARIANT.get(prefix)
    if not separator or not original_prefix or "/" in filename:
        return None
    parsed = _variant_from_filename(filename)
    if not parsed:
        return None
    original_filename, variant = parsed
    return f"{original_prefix}/{original_filename}", variant


def _local_variant_path(photo_path: str, variant: str) -> str:
    return os.path.join(
        os.path.dirname(photo_path),
        _LOCAL_VARIANT_DIRECTORY,
        f"{os.path.basename(photo_path)}.{OPTIONAL_VARIANT_VERSION}-{variant}.webp",
    )


def _is_local_optional_path(photo_path: str) -> bool:
    return os.path.basename(os.path.dirname(os.path.normpath(photo_path))) == "optionals"


def build_optional_variants(photo_path: str | None) -> dict[str, dict] | None:
    """URLs assinadas das variantes do opcional, com o maior lado nominal.

    Só a forma da URL é calculada aqui; a variante que ainda não existe no
    storage (acervo legado) é gerada na primeira leitura pela rota de mídia."""
    if not photo_path:
        return None
    object_key = _object_key_from_reference(photo_path)
    if object_key:
        keys = {
            variant: _optional_variant_key(object_key, variant)
            for variant in OPTIONAL_VARIANTS
        }
        if not all(keys.values()):
            return None
        return {
            variant: {
                "url": _signed_media_url(key),
                "max_side": OPTIONAL_VARIANTS[variant][0],
            }
            for variant, key in keys.items()
            if key
        }
    if not _is_local_optional_path(photo_path):
        return None
    variants = {}
    for variant, (max_side, _) in OPTIONAL_VARIANTS.items():
        url = build_photo_url(_local_variant_path(photo_path, variant))
        if not url:
            return None
        variants[variant] = {"url": url, "max_side": max_side}
    return variants


def _to_srgb(image: Image.Image, icc: bytes | None, target_mode: str) -> Image.Image:
    """Leva a imagem para sRGB no modo final. Com perfil próprio (Display P3,
    Adobe RGB, CMYK...), converte pelo perfil; sem perfil, ou com perfil
    ilegível, só troca o modo e mantém os valores."""
    if icc and image.mode in {"RGB", "RGBA", "CMYK"}:
        try:
            converted = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile("sRGB"),
                outputMode="RGBA" if image.mode == "RGBA" else "RGB",
            )
            if converted is not None:
                image = converted
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return image if image.mode == target_mode else image.convert(target_mode)


def _make_variant_bytes(content: bytes, variant: str) -> bytes:
    """Encaixe proporcional (contain) sem recorte, sem fundo e sem ampliar."""
    max_side, quality = OPTIONAL_VARIANTS[variant]
    with Image.open(io.BytesIO(content)) as source:
        # Uploads novos já passam pelo limite de pixels; isto protege o acervo
        # legado derivado sob demanda de alocar memória sem limite.
        if source.width * source.height > settings.MAX_IMAGE_PIXELS:
            raise ValueError("Imagem original acima do limite de pixels.")
        icc = source.info.get("icc_profile")
        has_alpha = source.mode in {"RGBA", "LA", "PA"} or (
            source.mode == "P" and "transparency" in source.info
        )
        image = _to_srgb(
            ImageOps.exif_transpose(source),
            icc,
            "RGBA" if has_alpha else "RGB",
        )
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=quality, method=6)
        return output.getvalue()


def _make_optional_variants(content: bytes) -> dict[str, bytes]:
    return {variant: _make_variant_bytes(content, variant) for variant in OPTIONAL_VARIANTS}


def image_max_side(content: bytes) -> int | None:
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = ImageOps.exif_transpose(image).size
            return max(width, height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _make_thumbnail_bytes(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail(
            (_THUMBNAIL_DIMENSION, _THUMBNAIL_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new(
            "RGB",
            (_THUMBNAIL_DIMENSION, _THUMBNAIL_DIMENSION),
            "white",
        )
        canvas.paste(
            image,
            (
                (_THUMBNAIL_DIMENSION - image.width) // 2,
                (_THUMBNAIL_DIMENSION - image.height) // 2,
            ),
        )
        output = io.BytesIO()
        canvas.save(output, format="WEBP", quality=76, method=6)
        return output.getvalue()


async def read_upload_limited(
    file: UploadFile,
    max_bytes: int,
    *,
    max_size_label: str,
) -> bytes:
    """Interrompe a leitura assim que o upload ultrapassa o limite."""

    content = bytearray()
    while chunk := await file.read(_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Arquivo excede {max_size_label}.",
            )
    return bytes(content)


def _sanitize_image_bytes(
    raw: bytes,
    allowed: set[str],
    max_bytes: int,
    max_pixels: int,
    max_dimension: int,
) -> tuple[bytes, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > max_pixels:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Imagem possui resolução acima do limite permitido.",
                )
            image.load()

        detected_ext = _FORMAT_TO_EXTENSION.get(image.format or "")
        if not detected_ext or detected_ext not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Conteúdo do arquivo não é uma imagem permitida.",
            )

        image = ImageOps.exif_transpose(image)
        if max(image.size) > max_dimension:
            image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )
        if detected_ext == "jpg" and image.mode != "RGB":
            image = image.convert("RGB")
        elif detected_ext in {"png", "webp"} and image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")

        output = io.BytesIO()
        save_format = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[detected_ext]
        save_options = (
            {"quality": 88, "optimize": True}
            if detected_ext in {"jpg", "webp"}
            else {"optimize": True}
        )
        image.save(output, format=save_format, **save_options)
        content = output.getvalue()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Imagem processada excede o limite permitido.",
            )
        return content, detected_ext
    except HTTPException:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Conteúdo do arquivo não é uma imagem válida.",
        )


async def sanitize_image_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    max_size_label: str,
    allowed_extensions: list[str],
    max_pixels: int = 25_000_000,
    max_dimension: int = 2560,
) -> tuple[bytes, str]:
    """Valida e regrava a imagem sem bloquear o event loop."""

    allowed = {
        "jpg" if extension.lower() == "jpeg" else extension.lower()
        for extension in allowed_extensions
    }
    supplied_ext = os.path.splitext(file.filename or "")[-1].lower().lstrip(".")
    supplied_ext = "jpg" if supplied_ext == "jpeg" else supplied_ext
    if supplied_ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Extensão '{supplied_ext}' não permitida.",
        )

    raw = await read_upload_limited(
        file,
        max_bytes,
        max_size_label=max_size_label,
    )
    async with _IMAGE_PROCESSING_SEMAPHORE:
        return await run_in_threadpool(
            _sanitize_image_bytes,
            raw,
            allowed,
            max_bytes,
            max_pixels,
            max_dimension,
        )


def _write_atomic(path: str, content: bytes, *, prefix: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=prefix, dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def _persist_upload(content: bytes, directory: str, extension: str) -> str:
    os.makedirs(directory, exist_ok=True)
    filename = f"{uuid.uuid4()}.{extension}"
    final_path = os.path.join(directory, filename)
    thumbnail_path = _local_thumbnail_path(final_path)
    thumbnail = _make_thumbnail_bytes(content)
    variants = (
        {
            _local_variant_path(final_path, name): data
            for name, data in _make_optional_variants(content).items()
        }
        if _is_local_optional_path(final_path)
        else {}
    )
    try:
        _write_atomic(final_path, content, prefix=".upload-")
        _write_atomic(thumbnail_path, thumbnail, prefix=".thumbnail-")
        for variant_path, data in variants.items():
            _write_atomic(variant_path, data, prefix=".variant-")
        return final_path
    except Exception:
        for candidate in (final_path, thumbnail_path, *variants):
            try:
                os.remove(candidate)
            except OSError:
                pass
        raise


def _persist_object_upload(
    content: bytes,
    directory: str,
    extension: str,
    market: str = "BR",
) -> str:
    directory_name = os.path.basename(os.path.normpath(directory))
    prefix = "optionals" if directory_name == "optionals" else "products"
    if market == "EU":
        prefix = f"eu-{prefix}"
    key = f"{prefix}/{uuid.uuid4()}.{extension}"
    thumbnail_key = _thumbnail_key_for_original(key)
    if not thumbnail_key:
        raise RuntimeError("Não foi possível derivar a chave da miniatura.")
    client, bucket = _storage_for_key(key)
    thumbnail = _make_thumbnail_bytes(content)
    derived = {thumbnail_key: thumbnail}
    if prefix in _VARIANT_PREFIX_BY_ORIGINAL:
        for name, data in _make_optional_variants(content).items():
            variant_key = _optional_variant_key(key, name)
            if variant_key:
                derived[variant_key] = data
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=_CONTENT_TYPES[extension],
            CacheControl="public, max-age=31536000, immutable",
        )
        for derived_key, data in derived.items():
            client.put_object(
                Bucket=bucket,
                Key=derived_key,
                Body=data,
                ContentType="image/webp",
                CacheControl="public, max-age=31536000, immutable",
            )
    except Exception:
        for candidate in (key, *derived):
            try:
                client.delete_object(Bucket=bucket, Key=candidate)
            except (BotoCoreError, ClientError):
                pass
        raise
    return _OBJECT_REFERENCE_PREFIX + key


async def persist_upload(
    content: bytes,
    directory: str,
    extension: str,
    *,
    market: str = "BR",
) -> str:
    if market == "EU":
        if settings.eu_object_storage_configured():
            return await run_in_threadpool(
                _persist_object_upload, content, directory, extension, "EU"
            )
        # Em produção, ausência do bucket do mercado é falha de configuração;
        # nunca grava no BR nem em disco efêmero.
        if (
            settings.object_storage_configured()
            or settings.persistent_media_storage_required()
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Armazenamento de fotos do mercado europeu não configurado.",
            )
        # Sem nenhum bucket (desenvolvimento e testes): disco local, sob `eu/`
        # na raiz de uploads -- `upload_belongs_to_market` reconhece por ali.
        relative = os.path.relpath(directory, settings.UPLOAD_DIR)
        directory = os.path.normpath(os.path.join(settings.UPLOAD_DIR, "eu", relative))
    elif settings.object_storage_configured():
        return await run_in_threadpool(
            _persist_object_upload,
            content,
            directory,
            extension,
        )
    elif settings.persistent_media_storage_required():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento persistente de fotos não configurado.",
        )
    return await run_in_threadpool(
        _persist_upload,
        content,
        directory,
        extension,
    )


def upload_belongs_to_market(path: str | None, market: str) -> bool:
    """Diz se o arquivo é do mercado informado.

    Durante a separação dos catálogos um produto EU pode ainda apontar para a
    foto do produto BR de origem, até a sincronização copiar o arquivo para o
    bucket europeu. Apagar essa referência apagaria a foto do Brasil."""
    if not path:
        return False
    object_key = _object_key_from_reference(path)
    if object_key:
        return _is_eu_key(object_key) == (market == "EU")
    local_key = _local_key_from_path(path) or ""
    return local_key.startswith("local/eu/") == (market == "EU")


def _delete_upload(path: str | None) -> None:
    if not path:
        return
    object_key = _object_key_from_reference(path)
    if object_key:
        if not _storage_configured_for_key(object_key):
            return
        client, bucket = _storage_for_key(object_key)
        thumbnail_key = _thumbnail_key_for_original(object_key)
        variant_keys = [
            _optional_variant_key(object_key, variant) for variant in OPTIONAL_VARIANTS
        ]
        for candidate in (object_key, thumbnail_key, *variant_keys):
            if not candidate:
                continue
            try:
                client.delete_object(Bucket=bucket, Key=candidate)
            except (BotoCoreError, ClientError):
                warnings.warn(
                    f"Não foi possível excluir o objeto {candidate!r}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return
    local_variants = (
        [_local_variant_path(path, variant) for variant in OPTIONAL_VARIANTS]
        if _is_local_optional_path(path)
        else []
    )
    for candidate in (path, _local_thumbnail_path(path), *local_variants):
        try:
            os.remove(candidate)
        except OSError:
            pass


async def delete_upload(path: str | None, *, market: str | None = None) -> None:
    """Remove o arquivo. Com `market`, só remove se o arquivo for daquele
    mercado -- referência emprestada de outro mercado fica intacta."""
    if market is not None and not upload_belongs_to_market(path, market):
        return
    await run_in_threadpool(_delete_upload, path)


def _storage_error_code(exc: Exception) -> str | None:
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code")
    return None


def _get_object_bytes(client, bucket: str, key: str) -> tuple[bytes, str]:
    """GET com nova tentativa quando a conexão cai durante a leitura do corpo."""
    for attempt in range(1, _STORAGE_READ_ATTEMPTS + 1):
        result = client.get_object(Bucket=bucket, Key=key)
        try:
            return result["Body"].read(), result.get(
                "ContentType",
                "application/octet-stream",
            )
        except _STORAGE_STREAM_ERRORS:
            if attempt == _STORAGE_READ_ATTEMPTS:
                raise
            time.sleep(0.1 * attempt)
    raise AssertionError("unreachable")


def _read_object_upload(object_key: str) -> tuple[bytes, str]:
    client, bucket = _storage_for_key(object_key)
    try:
        return _get_object_bytes(client, bucket, object_key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            original_key = _original_key_for_thumbnail(object_key)
            make_derived = _make_thumbnail_bytes
            if not original_key:
                parsed_variant = _original_key_for_variant(object_key)
                if not parsed_variant:
                    raise FileNotFoundError(object_key) from exc
                original_key, variant = parsed_variant
                make_derived = lambda data: _make_variant_bytes(data, variant)  # noqa: E731
            try:
                original, _ = _get_object_bytes(client, bucket, original_key)
            except ClientError as original_exc:
                original_error = original_exc.response.get("Error", {}).get("Code")
                if original_error in {"NoSuchKey", "404", "NotFound"}:
                    raise FileNotFoundError(original_key) from original_exc
                raise
            thumbnail = make_derived(original)
            # Gravar a miniatura é só cache: se falhar, a próxima leitura gera
            # de novo, e a imagem já gerada continua sendo servida.
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=object_key,
                    Body=thumbnail,
                    ContentType="image/webp",
                    CacheControl="public, max-age=31536000, immutable",
                )
            except (BotoCoreError, ClientError) as cache_exc:
                logger.warning(
                    "Miniatura gerada sem cache no storage: prefix=%s error=%s code=%s",
                    object_key.partition("/")[0],
                    type(cache_exc).__name__,
                    _storage_error_code(cache_exc),
                )
            return thumbnail, "image/webp"
        raise


async def read_object_upload(object_key: str) -> tuple[bytes, str]:
    prefix, separator, filename = object_key.partition("/")
    if (
        separator != "/"
        or prefix not in _OBJECT_KEY_PREFIXES
        or not filename
        or "/" in filename
    ):
        raise FileNotFoundError(object_key)
    if not _storage_configured_for_key(object_key):
        raise FileNotFoundError(object_key)
    async with _MEDIA_READ_SEMAPHORE:
        return await run_in_threadpool(_read_object_upload, object_key)


def _read_local_upload(local_key: str) -> tuple[bytes, str]:
    relative = local_key.removeprefix("local/")
    if not relative or "\\" in relative:
        raise FileNotFoundError(local_key)
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    candidate = (upload_root / relative).resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError as exc:
        raise FileNotFoundError(local_key) from exc
    if not candidate.is_file():
        return _derive_local_variant(candidate, upload_root, local_key)
    return candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"


def _derive_local_variant(candidate: Path, upload_root: Path, local_key: str) -> tuple[bytes, str]:
    """Variante local ausente (foto anterior às variantes): gera a partir da
    original vizinha. Só vale para `optionals/variants/`, dentro da raiz."""
    parsed = _variant_from_filename(candidate.name)
    if (
        not parsed
        or candidate.parent.name != _LOCAL_VARIANT_DIRECTORY
        or candidate.parent.parent.name != "optionals"
    ):
        raise FileNotFoundError(local_key)
    original_name, variant = parsed
    original = candidate.parent.parent / original_name
    try:
        original.relative_to(upload_root)
    except ValueError as exc:
        raise FileNotFoundError(local_key) from exc
    if not original.is_file():
        raise FileNotFoundError(local_key)
    data = _make_variant_bytes(original.read_bytes(), variant)
    try:
        _write_atomic(str(candidate), data, prefix=".variant-")
    except OSError:
        logger.warning("Variante local gerada sem cache em disco: variant=%s", variant)
    return data, "image/webp"


async def read_media_upload(object_key: str) -> tuple[bytes, str]:
    if object_key.startswith("local/"):
        return await run_in_threadpool(_read_local_upload, object_key)
    return await read_object_upload(object_key)


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            return False
        raise


def _inspect_optional_variants(photo_path: str, apply: bool) -> dict:
    object_key = _object_key_from_reference(photo_path)
    if object_key:
        if not _storage_configured_for_key(object_key):
            raise FileNotFoundError(object_key)
        client, bucket = _storage_for_key(object_key)
        targets = {
            variant: _optional_variant_key(object_key, variant)
            for variant in OPTIONAL_VARIANTS
        }
        if not all(targets.values()):
            raise ValueError("Referência não é de opcional.")
        content = client.get_object(Bucket=bucket, Key=object_key)["Body"].read()
        missing = [v for v, key in targets.items() if not _object_exists(client, bucket, key)]

        def write(variant: str, data: bytes) -> None:
            client.put_object(
                Bucket=bucket,
                Key=targets[variant],
                Body=data,
                ContentType="image/webp",
                CacheControl="public, max-age=31536000, immutable",
            )
    else:
        local_key = _local_key_from_path(photo_path)
        if not local_key or not _is_local_optional_path(photo_path):
            raise FileNotFoundError(photo_path)
        content, _ = _read_local_upload(local_key)
        targets = {v: _local_variant_path(photo_path, v) for v in OPTIONAL_VARIANTS}
        missing = [v for v, path in targets.items() if not os.path.isfile(path)]

        def write(variant: str, data: bytes) -> None:
            _write_atomic(targets[variant], data, prefix=".variant-")

    generated = []
    if apply:
        for variant in missing:
            write(variant, _make_variant_bytes(content, variant))
            generated.append(variant)
    max_side = image_max_side(content)
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "max_side": max_side,
        "low_resolution": max_side is not None and max_side < OPTIONAL_RECOMMENDED_MIN_SIDE,
        "missing": [v for v in missing if v not in generated],
        "generated": generated,
    }


async def inspect_optional_variants(photo_path: str, *, apply: bool) -> dict:
    """Inventário de uma foto de opcional e, com `apply`, gera as variantes que
    faltam. Chaves determinísticas: repetir não duplica nem sobrescreve."""
    async with _IMAGE_PROCESSING_SEMAPHORE:
        return await run_in_threadpool(_inspect_optional_variants, photo_path, apply)


async def copy_upload_to_market(path: str, *, kind: str, market: str = "EU") -> str:
    """Copia a foto para o armazenamento do mercado e devolve a nova referência.

    A origem não é tocada: ela continua sendo a foto do catálogo brasileiro.
    Os dois buckets têm credenciais próprias, então não há CopyObject entre
    eles -- o arquivo passa pela API (lê de um, grava no outro, com miniatura).
    """
    if kind not in {"products", "optionals"}:
        raise ValueError(f"Tipo de mídia desconhecido: {kind!r}")
    object_key = _object_key_from_reference(path)
    if object_key:
        content, _ = await read_object_upload(object_key)
        extension = object_key.rsplit(".", 1)[-1].lower()
    else:
        local_key = _local_key_from_path(path)
        if not local_key:
            raise FileNotFoundError(path)
        content, _ = await run_in_threadpool(_read_local_upload, local_key)
        extension = path.rsplit(".", 1)[-1].lower()
    extension = "jpg" if extension == "jpeg" else extension
    if extension not in _CONTENT_TYPES:
        raise ValueError(f"Extensão de imagem não suportada: {extension!r}")
    directory = (
        os.path.join(settings.UPLOAD_DIR, "optionals")
        if kind == "optionals"
        else settings.UPLOAD_DIR
    )
    return await persist_upload(content, directory, extension, market=market)
