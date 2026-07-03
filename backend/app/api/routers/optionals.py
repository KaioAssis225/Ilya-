import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, require_roles
from app.models.optional_color import OptionalColor
from app.models.user import User, UserRole
from app.schemas.optional import OptionalColorCreate, OptionalColorUpdate, OptionalColorRead
from app.core.config import settings

def _detect_mime(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None

router = APIRouter(prefix="/api/v1/optionals", tags=["optionals"])

_ADMIN_VENDEDOR = Depends(require_roles(UserRole.admin, UserRole.vendedor))
_ADMIN = Depends(require_roles(UserRole.admin))
_ANY = Depends(require_roles(UserRole.admin, UserRole.vendedor, UserRole.representante))


def _build_photo_url(photo_path: Optional[str]) -> Optional[str]:
    if not photo_path:
        return None
    if photo_path.startswith("app/"):
        return "/" + photo_path[4:]
    return "/static/uploads/" + os.path.basename(photo_path)


def _to_read(opt: OptionalColor) -> OptionalColorRead:
    data = OptionalColorRead.model_validate(opt)
    data.photo_url = _build_photo_url(opt.photo_path)
    return data


@router.get("", response_model=List[OptionalColorRead])
async def list_optionals(
    category: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, le=5000),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ANY,
):
    stmt = select(OptionalColor)
    if category:
        stmt = stmt.where(OptionalColor.category == category)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return [_to_read(o) for o in result.scalars().all()]


@router.post("", response_model=OptionalColorRead, status_code=status.HTTP_201_CREATED)
async def create_optional(
    payload: OptionalColorCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    opt = OptionalColor(**payload.model_dump())
    db.add(opt)
    await db.commit()
    await db.refresh(opt)
    return _to_read(opt)


@router.patch("/{optional_id}", response_model=OptionalColorRead)
async def update_optional(
    optional_id: uuid.UUID,
    payload: OptionalColorUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(OptionalColor).where(OptionalColor.id == optional_id))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opt, field, value)
    await db.commit()
    await db.refresh(opt)
    return _to_read(opt)


@router.delete("/{optional_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_optional(
    optional_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(select(OptionalColor).where(OptionalColor.id == optional_id))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    await db.delete(opt)
    await db.commit()


@router.post("/{optional_id}/upload-photo", response_model=OptionalColorRead)
async def upload_photo(
    optional_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN_VENDEDOR,
):
    result = await db.execute(select(OptionalColor).where(OptionalColor.id == optional_id))
    opt = result.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opcional não encontrado.")
    ext = os.path.splitext(file.filename or "")[-1].lower().lstrip(".")
    if ext not in settings.get_allowed_extensions():
        raise HTTPException(status_code=422, detail=f"Extensão '{ext}' não permitida.")
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")
    detected = _detect_mime(content)
    if detected is None or detected not in settings.get_allowed_extensions():
        raise HTTPException(status_code=422, detail="Conteúdo do arquivo não é uma imagem válida.")
    if opt.photo_path and os.path.exists(opt.photo_path):
        os.remove(opt.photo_path)
    filename = f"{uuid.uuid4()}.{ext}"
    opt_dir = os.path.join(settings.UPLOAD_DIR, "optionals")
    os.makedirs(opt_dir, exist_ok=True)
    save_path = os.path.join(opt_dir, filename)
    with open(save_path, "wb") as f:
        f.write(content)
    opt.photo_path = f"app/static/uploads/optionals/{filename}"
    await db.commit()
    await db.refresh(opt)
    return _to_read(opt)
