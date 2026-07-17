import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user, require_roles, is_internal_operator
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.representative import RepresentativeCreate, RepresentativeUpdate, RepresentativeRead

router = APIRouter(prefix="/api/v1/representatives", tags=["representatives"])

_ADMIN = Depends(require_roles(UserRole.admin))


async def _linked_ids(db: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    result = await db.execute(select(User.linked_id).where(User.linked_id.in_(ids)))
    return {row[0] for row in result.fetchall() if row[0] is not None}


def _with_has_user(rep: Representative, linked: set[uuid.UUID]) -> RepresentativeRead:
    r = RepresentativeRead.model_validate(rep)
    return r.model_copy(update={"has_user": rep.id in linked})


@router.get("", response_model=List[RepresentativeRead])
async def list_representatives(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            return []
        result = await db.execute(
            select(Representative).where(Representative.id == current_user.rep_id)
        )
    else:
        result = await db.execute(select(Representative).offset(skip).limit(limit))
    reps = result.scalars().all()
    linked = await _linked_ids(db, [r.id for r in reps])
    return [_with_has_user(r, linked) for r in reps]


@router.post("", response_model=RepresentativeRead, status_code=status.HTTP_201_CREATED)
async def create_representative(
    payload: RepresentativeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_roles(UserRole.admin)),
):
    rep = Representative(**payload.model_dump())
    db.add(rep)
    await db.commit()
    await db.refresh(rep)
    return RepresentativeRead.model_validate(rep)


@router.get("/{rep_id}", response_model=RepresentativeRead)
async def get_representative(
    rep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.representante and current_user.rep_id != rep_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este representante.")
    result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")
    linked = await _linked_ids(db, [rep.id])
    return _with_has_user(rep, linked)


@router.patch("/{rep_id}", response_model=RepresentativeRead)
async def update_representative(
    rep_id: uuid.UUID,
    payload: RepresentativeUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if not (current_user.role == UserRole.admin or is_internal_operator(current_user)):
        if current_user.role != UserRole.representante or current_user.rep_id != rep_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação não permitida para o seu nível de acesso.")
    result = await db.execute(select(Representative).where(Representative.id == rep_id))
    rep = result.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")
    update_data = payload.model_dump(exclude_unset=True)
    if current_user.role == UserRole.representante:
        update_data.pop("email", None)
    if current_user.role != UserRole.admin:
        update_data.pop("max_discount", None)
    for field, value in update_data.items():
        setattr(rep, field, value)
    await db.commit()
    await db.refresh(rep)
    linked = await _linked_ids(db, [rep.id])
    return _with_has_user(rep, linked)


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
