import asyncio
import hashlib
import hmac
import io
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
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings


_CHUNK_SIZE = 64 * 1024
_FORMAT_TO_EXTENSION = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_IMAGE_PROCESSING_SEMAPHORE = asyncio.Semaphore(2)
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
_EU_KEY_PREFIXES = _EU_ORIGINAL_PREFIXES | {
    _THUMBNAIL_PREFIX_BY_ORIGINAL[prefix] for prefix in _EU_ORIGINAL_PREFIXES
}
_ORIGINAL_PREFIX_BY_THUMBNAIL = {
    thumbnail: original
    for original, thumbnail in _THUMBNAIL_PREFIX_BY_ORIGINAL.items()
}
_OBJECT_KEY_PREFIXES = (
    _ORIGINAL_OBJECT_KEY_PREFIXES | set(_ORIGINAL_PREFIX_BY_THUMBNAIL)
)
_THUMBNAIL_DIMENSION = 320
_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _media_signature(object_key: str, expires: int) -> str:
    payload = f"{object_key}\n{expires}".encode("utf-8")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


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
    return hmac.compare_digest(_media_signature(object_key, expires), signature)


def _signed_media_url(object_key: str, *, now: int | None = None) -> str:
    current = int(time.time()) if now is None else now
    expires = current + settings.MEDIA_URL_TTL_SECONDS
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


@lru_cache(maxsize=1)
def _object_storage_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
        aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        region_name=settings.OBJECT_STORAGE_REGION,
        config=Config(
            signature_version="s3v4",
            s3={
                "addressing_style": _normalized_addressing_style(
                    settings.OBJECT_STORAGE_ADDRESSING_STYLE
                )
            },
        ),
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
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": _normalized_addressing_style(style)},
        ),
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
    try:
        _write_atomic(final_path, content, prefix=".upload-")
        _write_atomic(thumbnail_path, thumbnail, prefix=".thumbnail-")
        return final_path
    except Exception:
        for candidate in (final_path, thumbnail_path):
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
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=_CONTENT_TYPES[extension],
            CacheControl="public, max-age=31536000, immutable",
        )
        client.put_object(
            Bucket=bucket,
            Key=thumbnail_key,
            Body=thumbnail,
            ContentType="image/webp",
            CacheControl="public, max-age=31536000, immutable",
        )
    except Exception:
        for candidate in (key, thumbnail_key):
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
        # Com o principal em objetos e o europeu ausente, gravar EU no bucket
        # brasileiro desfaria a separação sem ninguém perceber. Recusa.
        if settings.object_storage_configured():
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
        for candidate in (object_key, thumbnail_key):
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
    for candidate in (path, _local_thumbnail_path(path)):
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


def _read_object_upload(object_key: str) -> tuple[bytes, str]:
    client, bucket = _storage_for_key(object_key)
    try:
        result = client.get_object(
            Bucket=bucket,
            Key=object_key,
        )
        return result["Body"].read(), result.get(
            "ContentType",
            "application/octet-stream",
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            original_key = _original_key_for_thumbnail(object_key)
            if not original_key:
                raise FileNotFoundError(object_key) from exc
            try:
                original = client.get_object(
                    Bucket=bucket,
                    Key=original_key,
                )["Body"].read()
            except ClientError as original_exc:
                original_error = original_exc.response.get("Error", {}).get("Code")
                if original_error in {"NoSuchKey", "404", "NotFound"}:
                    raise FileNotFoundError(original_key) from original_exc
                raise
            thumbnail = _make_thumbnail_bytes(original)
            client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=thumbnail,
                ContentType="image/webp",
                CacheControl="public, max-age=31536000, immutable",
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
        raise FileNotFoundError(local_key)
    return candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"


async def read_media_upload(object_key: str) -> tuple[bytes, str]:
    if object_key.startswith("local/"):
        return await run_in_threadpool(_read_local_upload, object_key)
    return await read_object_upload(object_key)


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
