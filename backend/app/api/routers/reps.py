import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.representative import RepresentativeCreate, RepresentativeUpdate, RepresentativeRead

router = APIRouter(prefix="/api/v1/representatives", tags=["representatives"])

_ADMIN = Depends(require_roles(UserRole.admin))


@router.get("", response_model=List[RepresentativeRead])
async def list_representatives(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    # HIGH-05: representante só vê o próprio registro
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            return []
        result = await db.execute(
            select(Representative).where(Representative.id == current_user.rep_id)
        )
        return result.scalars().all()
    result = await db.execute(select(Representative).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=RepresentativeRead, status_code=status.HTTP_201_CREATED)
async def create_representative(
    payload: RepresentativeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_roles(UserRole.admin, UserRole.vendedor)),
):
    rep = Representative(**payload.model_dump())
    db.add(rep)
    await db.commit()
    await db.refresh(rep)
    return rep


@router.get("/{rep_id}", response_model=RepresentativeRead)
async def get_representative(
    rep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    # HIGH-05: representante só acessa o próprio registro
    if current_user.role == UserRole.representante and current_user.rep_id != rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este representante.")
    result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")
    return rep


@router.patch("/{rep_id}", response_model=RepresentativeRead)
async def update_representative(
    rep_id: uuid.UUID,
    payload: RepresentativeUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.vendedor]:
        if current_user.role != UserRole.representante or current_user.rep_id != rep_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operação não permitida para o seu nível de acesso."
            )
    result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rep, field, value)
    await db.commit()
    await db.refresh(rep)
    return rep


@router.delete("/{rep_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_representative(
    rep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")
    await db.delete(rep)
    await db.commit()
