import logging
import time

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.core.uploads import read_media_upload, verify_media_signature


logger = logging.getLogger("ilya.media")


router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/{object_key:path}", include_in_schema=False)
async def get_media(object_key: str, expires: int, signature: str) -> Response:
    if not verify_media_signature(object_key, expires, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Link de imagem inválido ou expirado.",
        )
    try:
        content, content_type = await read_media_upload(object_key)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagem não encontrada.",
        )
    except (BotoCoreError, ClientError) as exc:
        # Só prefixo, tipo e código: a chave completa e a assinatura ficam fora do log.
        logger.warning(
            "Falha de storage ao servir mídia: prefix=%s error=%s code=%s",
            object_key.partition("/")[0],
            type(exc).__name__,
            exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento de imagens temporariamente indisponível.",
        )
    return Response(
        content=content,
        media_type=content_type,
        headers={
            # A chave do objeto nunca é reescrita (foto nova = chave nova) e a
            # URL é estável dentro da janela de validade: sem revalidar.
            "Cache-Control": f"private, max-age={max(0, expires - int(time.time()))}, immutable",
            "Referrer-Policy": "no-referrer",
        },
    )
