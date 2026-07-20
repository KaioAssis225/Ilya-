import asyncio
import io
import os
import tempfile
import uuid
import warnings
from functools import lru_cache
from urllib.parse import quote

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
_OBJECT_KEY_PREFIXES = {"products", "optionals"}
_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


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
            s3={"addressing_style": settings.OBJECT_STORAGE_ADDRESSING_STYLE},
        ),
    )


def _object_key_from_reference(reference: str | None) -> str | None:
    if not reference or not reference.startswith(_OBJECT_REFERENCE_PREFIX):
        return None
    key = reference[len(_OBJECT_REFERENCE_PREFIX):]
    prefix, separator, filename = key.partition("/")
    if (
        separator != "/"
        or prefix not in _OBJECT_KEY_PREFIXES
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
        return "/api/v1/media/" + quote(object_key, safe="/")
    if photo_path.startswith("app/"):
        return "/" + photo_path[4:]
    return "/static/uploads/" + os.path.basename(photo_path)


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
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Imagem possui resolução acima do limite permitido.",
                )
            image.load()

        detected_ext = _FORMAT_TO_EXTENSION.get(image.format or "")
        if not detected_ext or detected_ext not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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


def _persist_upload(content: bytes, directory: str, extension: str) -> str:
    os.makedirs(directory, exist_ok=True)
    filename = f"{uuid.uuid4()}.{extension}"
    final_path = os.path.join(directory, filename)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".upload-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, final_path)
        return final_path
    except Exception:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def _persist_object_upload(content: bytes, directory: str, extension: str) -> str:
    directory_name = os.path.basename(os.path.normpath(directory))
    prefix = "optionals" if directory_name == "optionals" else "products"
    key = f"{prefix}/{uuid.uuid4()}.{extension}"
    _object_storage_client().put_object(
        Bucket=settings.OBJECT_STORAGE_BUCKET,
        Key=key,
        Body=content,
        ContentType=_CONTENT_TYPES[extension],
        CacheControl="public, max-age=31536000, immutable",
    )
    return _OBJECT_REFERENCE_PREFIX + key


async def persist_upload(content: bytes, directory: str, extension: str) -> str:
    if settings.object_storage_configured():
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


def _delete_upload(path: str | None) -> None:
    if not path:
        return
    object_key = _object_key_from_reference(path)
    if object_key:
        if not settings.object_storage_configured():
            return
        try:
            _object_storage_client().delete_object(
                Bucket=settings.OBJECT_STORAGE_BUCKET,
                Key=object_key,
            )
        except (BotoCoreError, ClientError):
            warnings.warn(
                f"Não foi possível excluir o objeto {object_key!r}.",
                RuntimeWarning,
                stacklevel=2,
            )
        return
    try:
        os.remove(path)
    except OSError:
        pass


async def delete_upload(path: str | None) -> None:
    await run_in_threadpool(_delete_upload, path)


def _read_object_upload(object_key: str) -> tuple[bytes, str]:
    try:
        result = _object_storage_client().get_object(
            Bucket=settings.OBJECT_STORAGE_BUCKET,
            Key=object_key,
        )
        return result["Body"].read(), result.get(
            "ContentType",
            "application/octet-stream",
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            raise FileNotFoundError(object_key) from exc
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
    if not settings.object_storage_configured():
        raise FileNotFoundError(object_key)
    return await run_in_threadpool(_read_object_upload, object_key)
