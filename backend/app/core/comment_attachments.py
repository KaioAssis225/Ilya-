import logging
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings


logger = logging.getLogger("ilya.comment_attachments")


def _require_storage() -> None:
    if not settings.comment_attachment_storage_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento de anexos temporariamente indisponível.",
        )


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.COMMENT_ATTACHMENTS_ENDPOINT,
        aws_access_key_id=settings.COMMENT_ATTACHMENTS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.COMMENT_ATTACHMENTS_SECRET_ACCESS_KEY,
        region_name=settings.COMMENT_ATTACHMENTS_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.COMMENT_ATTACHMENTS_ADDRESSING_STYLE},
            retries={"mode": "standard", "max_attempts": 4},
            connect_timeout=5,
            read_timeout=30,
            tcp_keepalive=True,
        ),
    )


async def put_comment_attachment(
    object_key: str, content: bytes, content_type: str
) -> None:
    _require_storage()

    def put() -> None:
        _client().put_object(
            Bucket=settings.COMMENT_ATTACHMENTS_BUCKET,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    try:
        await run_in_threadpool(put)
    except (BotoCoreError, ClientError):
        logger.exception("Falha ao gravar anexo privado: key=%s", object_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível armazenar o anexo. Tente novamente.",
        )


async def get_comment_attachment(object_key: str) -> bytes:
    _require_storage()

    def get() -> bytes:
        response = _client().get_object(
            Bucket=settings.COMMENT_ATTACHMENTS_BUCKET,
            Key=object_key,
        )
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    try:
        return await run_in_threadpool(get)
    except (BotoCoreError, ClientError):
        logger.exception("Falha ao ler anexo privado: key=%s", object_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível carregar o anexo. Tente novamente.",
        )


async def delete_comment_attachment(object_key: str) -> None:
    if not settings.comment_attachment_storage_configured():
        logger.error("Bucket de anexos não configurado ao excluir key=%s", object_key)
        return

    def delete() -> None:
        _client().delete_object(
            Bucket=settings.COMMENT_ATTACHMENTS_BUCKET,
            Key=object_key,
        )

    try:
        await run_in_threadpool(delete)
    except (BotoCoreError, ClientError):
        # A linha de banco já não referencia o objeto. O log permite a
        # limpeza operacional posterior sem reabrir a transação comercial.
        logger.exception("Anexo órfão pendente de limpeza: key=%s", object_key)
