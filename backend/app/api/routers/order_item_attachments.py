import logging
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_principal, get_current_user, get_db_session
from app.core.comment_attachments import (
    delete_comment_attachment,
    get_comment_attachment,
    put_comment_attachment,
)
from app.core.config import settings
from app.core.markets import MarketPrincipal
from app.core.uploads import read_upload_limited, sanitize_image_upload
from app.models.order import Order, OrderItem
from app.models.order_item_attachment import OrderItemAttachment
from app.models.user import User
from app.schemas.order import OrderItemAttachmentRead


router = APIRouter(
    prefix="/api/v1/order-item-attachments", tags=["order-item-attachments"]
)
logger = logging.getLogger("ilya.order_item_attachments")

_IMAGE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_SAFE_FILENAME = re.compile(r"[^\w._ -]+", re.UNICODE)


def _filename(value: str | None, extension: str) -> str:
    raw = Path(value or f"anexo.{extension}").name.strip()
    stem = _SAFE_FILENAME.sub("_", Path(raw).stem).strip(" ._") or "anexo"
    return f"{stem[:220]}.{extension}"


async def _validated_content(file: UploadFile) -> tuple[bytes, str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    max_bytes = settings.COMMENT_ATTACHMENTS_MAX_MB * 1024 * 1024
    max_label = f"{settings.COMMENT_ATTACHMENTS_MAX_MB}MB"
    if suffix == ".pdf":
        content = await read_upload_limited(file, max_bytes, max_size_label=max_label)
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="O arquivo não é um PDF válido.",
            )
        return content, "pdf", "application/pdf"
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        content, extension = await sanitize_image_upload(
            file,
            max_bytes=max_bytes,
            max_size_label=max_label,
            allowed_extensions=["jpg", "jpeg", "png", "webp"],
            max_pixels=settings.MAX_IMAGE_PIXELS,
            max_dimension=settings.MAX_IMAGE_DIMENSION,
        )
        return content, extension, _IMAGE_CONTENT_TYPES[extension]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Envie uma foto JPG, PNG ou WebP, ou um documento PDF.",
    )


async def _can_read_attached(
    db: AsyncSession,
    attachment: OrderItemAttachment,
    current_user: User,
    principal: MarketPrincipal,
) -> bool:
    # Import local evita acoplamento circular no carregamento dos routers.
    from app.api.routers.orders import _order_visibility_filters

    if attachment.order_item_id is None:
        return attachment.uploaded_by_user_id == current_user.id
    return (
        await db.execute(
            select(Order.id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                OrderItem.id == attachment.order_item_id,
                Order.market_code == principal.code,
                *_order_visibility_filters(current_user),
            )
        )
    ).scalar_one_or_none() is not None


@router.post("", response_model=OrderItemAttachmentRead, status_code=201)
async def upload_order_item_attachment(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    content, extension, content_type = await _validated_content(file)
    original_filename = _filename(file.filename, extension)
    attachment_id = uuid.uuid4()
    object_key = (
        f"{principal.code.lower()}/pending/{current_user.id}/"
        f"{attachment_id}/{original_filename}"
    )
    await put_comment_attachment(object_key, content, content_type)
    attachment = OrderItemAttachment(
        id=attachment_id,
        market_code=principal.code,
        uploaded_by_user_id=current_user.id,
        object_key=object_key,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(content),
    )
    db.add(attachment)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await delete_comment_attachment(object_key)
        logger.exception(
            "Falha ao registrar metadados do anexo: key=%s user=%s",
            object_key,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível concluir o envio do anexo. Tente novamente.",
        )
    await db.refresh(attachment)
    return attachment


@router.get("/{attachment_id}")
async def download_order_item_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    attachment = await db.get(OrderItemAttachment, attachment_id)
    if (
        attachment is None
        or attachment.market_code != principal.code
        or not await _can_read_attached(db, attachment, current_user, principal)
    ):
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    content = await get_comment_attachment(attachment.object_key)
    encoded = quote(attachment.original_filename, safe="")
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_pending_order_item_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    attachment = await db.get(OrderItemAttachment, attachment_id)
    if (
        attachment is None
        or attachment.market_code != principal.code
        or attachment.order_item_id is not None
        or attachment.uploaded_by_user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Anexo pendente não encontrado.")
    object_key = attachment.object_key
    await db.delete(attachment)
    await db.commit()
    await delete_comment_attachment(object_key)
