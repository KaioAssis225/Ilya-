from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.core.uploads import read_object_upload


router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/{object_key:path}", include_in_schema=False)
async def get_media(object_key: str) -> Response:
    try:
        content, content_type = await read_object_upload(object_key)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagem não encontrada.",
        )
    except (BotoCoreError, ClientError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Armazenamento de imagens temporariamente indisponível.",
        )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
