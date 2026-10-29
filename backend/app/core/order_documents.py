"""Armazenamento privado dos PDFs de pedido."""
import hashlib
import re
import uuid
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.uploads import _eu_object_storage_client, _object_storage_client, _write_atomic


_KEY_RE = re.compile(
    r"^order-documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}/v[1-9][0-9]*-[0-9a-f]{16}\.pdf$"
)


class OrderDocumentStorageError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_market(market: str) -> None:
    if market not in {"BR", "EU"}:
        raise OrderDocumentStorageError("invalid_market")


def _validate_key(storage_key: str) -> None:
    if not _KEY_RE.fullmatch(storage_key):
        raise OrderDocumentStorageError("invalid_storage_key")


def _storage(market: str):
    _validate_market(market)
    if (
        settings.object_storage_partially_configured()
        or settings.eu_object_storage_partially_configured()
    ):
        raise OrderDocumentStorageError("storage_not_configured")
    if market == "EU" and settings.eu_object_storage_configured():
        return _eu_object_storage_client(), settings.OBJECT_STORAGE_EU_BUCKET
    if market == "BR" and settings.object_storage_configured():
        return _object_storage_client(), settings.OBJECT_STORAGE_BUCKET
    if not settings.object_storage_configured() and not settings.eu_object_storage_configured():
        if settings.DEBUG:
            return None
        raise OrderDocumentStorageError("storage_not_configured")
    # Nunca usa o bucket do outro mercado como fallback.
    raise OrderDocumentStorageError("storage_not_configured")


def _local_path(market: str, storage_key: str) -> Path:
    root = Path(settings.ORDER_EMAIL_LOCAL_DIR).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    try:
        root.relative_to(upload_root)
    except ValueError:
        pass
    else:
        raise OrderDocumentStorageError("storage_not_configured")
    candidate = (root / market / storage_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise OrderDocumentStorageError("invalid_storage_key")
    return candidate


async def put_document(
    market: str,
    order_id: uuid.UUID,
    version: int,
    content: bytes,
) -> tuple[str, str, int]:
    _validate_market(market)
    digest = hashlib.sha256(content).hexdigest()
    storage_key = f"order-documents/{order_id}/v{version}-{digest[:16]}.pdf"
    _validate_key(storage_key)
    selected = _storage(market)
    try:
        if selected is None:
            path = _local_path(market, storage_key)
            await run_in_threadpool(
                _write_atomic,
                str(path),
                content,
                prefix=".order-document-",
            )
        else:
            client, bucket = selected
            await run_in_threadpool(
                client.put_object,
                Bucket=bucket,
                Key=storage_key,
                Body=content,
                ContentType="application/pdf",
            )
    except OrderDocumentStorageError:
        raise
    except Exception:
        raise OrderDocumentStorageError("storage_unavailable")
    return storage_key, digest, len(content)


def _read_object(client, bucket: str, storage_key: str) -> bytes:
    result = client.get_object(Bucket=bucket, Key=storage_key)
    body = result["Body"]
    if isinstance(body, bytes):
        return body
    try:
        return body.read()
    finally:
        close = getattr(body, "close", None)
        if close:
            close()


async def get_document(market: str, storage_key: str) -> bytes:
    _validate_market(market)
    _validate_key(storage_key)
    selected = _storage(market)
    try:
        if selected is None:
            return await run_in_threadpool(_local_path(market, storage_key).read_bytes)
        client, bucket = selected
        return await run_in_threadpool(_read_object, client, bucket, storage_key)
    except OrderDocumentStorageError:
        raise
    except FileNotFoundError:
        raise OrderDocumentStorageError("document_not_found")
    except Exception:
        raise OrderDocumentStorageError("storage_unavailable")
