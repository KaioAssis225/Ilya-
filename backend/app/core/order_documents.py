"""Armazenamento privado e imutável dos PDFs finalizados."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from starlette.concurrency import run_in_threadpool

from app.core.config import settings


def document_key(market: str, order_id: uuid.UUID, version: int, sha256: str) -> str:
    prefix = "eu-order-documents" if market == "EU" else "order-documents"
    return f"{prefix}/{order_id}/v{version}/{sha256}.pdf"


def _client_and_bucket(market: str):
    if market == "EU":
        if not settings.eu_object_storage_configured():
            return None
        endpoint = settings.OBJECT_STORAGE_EU_ENDPOINT
        access_key = settings.OBJECT_STORAGE_EU_ACCESS_KEY_ID
        secret = settings.OBJECT_STORAGE_EU_SECRET_ACCESS_KEY
        region = settings.OBJECT_STORAGE_EU_REGION
        bucket = settings.OBJECT_STORAGE_EU_BUCKET
        style = settings.OBJECT_STORAGE_EU_ADDRESSING_STYLE or settings.OBJECT_STORAGE_ADDRESSING_STYLE
    else:
        if not settings.object_storage_configured():
            return None
        endpoint = settings.OBJECT_STORAGE_ENDPOINT
        access_key = settings.OBJECT_STORAGE_ACCESS_KEY_ID
        secret = settings.OBJECT_STORAGE_SECRET_ACCESS_KEY
        region = settings.OBJECT_STORAGE_REGION
        bucket = settings.OBJECT_STORAGE_BUCKET
        style = settings.OBJECT_STORAGE_ADDRESSING_STYLE
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual" if style == "virtual-host" else style},
        ),
    )
    return client, bucket


def _local_path(key: str) -> Path:
    root = (Path(settings.UPLOAD_DIR) / "private").resolve()
    candidate = (root / Path(key)).resolve()
    candidate.relative_to(root)
    return candidate


def _write_local(key: str, content: bytes) -> None:
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".order-pdf-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _persist(key: str, market: str, content: bytes) -> None:
    storage = _client_and_bucket(market)
    if storage is None:
        if settings.persistent_media_storage_required():
            raise RuntimeError(f"Armazenamento privado do mercado {market} não configurado.")
        _write_local(key, content)
        return
    client, bucket = storage
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType="application/pdf",
        CacheControl="private, max-age=31536000, immutable",
        Metadata={"sha256": key.rsplit("/", 1)[-1].removesuffix(".pdf")},
    )


def _read(key: str, market: str) -> bytes:
    storage = _client_and_bucket(market)
    if storage is None:
        return _local_path(key).read_bytes()
    client, bucket = storage
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


async def persist_order_pdf(key: str, market: str, content: bytes) -> None:
    await run_in_threadpool(_persist, key, market, content)


async def read_order_pdf(key: str, market: str) -> bytes:
    return await run_in_threadpool(_read, key, market)
