import uuid
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, or_, select

from app.api.deps import get_db_session, get_current_user, require_roles, is_client_account, is_internal_operator
from app.core.search import literal_contains_pattern
from app.models.client import Client
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.representative import RepresentativeCreate, RepresentativeUpdate, RepresentativeRead

router = APIRouter(prefix="/api/v1/representatives", tags=["representatives"])

_ADMIN = Depends(require_roles(UserRole.admin))


async def _linked_ids(db: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    result = await db.execute(
        select(User.linked_id).where(User.linked_id.in_(ids))
    )
    return {row[0] for row in result.fetchall() if row[0] is not None}


def _with_has_user(rep: Representative, linked: set[uuid.UUID]) -> RepresentativeRead:
    r = RepresentativeRead.model_validate(rep)
    return r.model_copy(update={"has_user": rep.id in linked})


@router.get("", response_model=List[RepresentativeRead])
async def list_representatives(
    response: Response,
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=100, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    include_total: bool = Query(default=True),
    sort_by: Literal[
        "name",
        "email",
        "phone",
        "city",
        "state",
        "max_discount",
    ] = Query(default="name"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    filters = []
    if current_user.role == UserRole.representante:
        if not current_user.rep_id:
            response.headers["X-Total-Count"] = "0"
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        filters.append(Representative.id == current_user.rep_id)
    elif is_client_account(current_user):
        if not current_user.linked_id:
            response.headers["X-Total-Count"] = "0"
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        client_rep_id = (
            await db.execute(
                select(Client.rep_id)
                .where(Client.id == current_user.linked_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not client_rep_id:
            response.headers["X-Total-Count"] = "0"
            response.headers["X-Has-More"] = "false"
            response.headers["X-Page-Size"] = "0"
            return []
        filters.append(Representative.id == client_rep_id)

    search = q.strip() if q else ""
    if search:
        search_pattern = literal_contains_pattern(search)
        filters.append(
            or_(
                Representative.name.ilike(search_pattern, escape="\\"),
                Representative.email.ilike(search_pattern, escape="\\"),
                Representative.city.ilike(search_pattern, escape="\\"),
            )
        )

    sort_column = {
        "name": Representative.name,
        "email": Representative.email,
        "phone": Representative.phone,
        "city": Representative.city,
        "state": Representative.state,
        "max_discount": Representative.max_discount,
    }[sort_by]
    order_expression = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    id_order = (
        Representative.id.desc()
        if sort_dir == "desc"
        else Representative.id.asc()
    )

    total: int | None = None
    if include_total:
        total = (
            await db.execute(
                select(func.count())
                .select_from(Representative)
                .where(*filters)
            )
        ).scalar_one()
    result = await db.execute(
        select(Representative)
        .where(*filters)
        .order_by(order_expression, id_order)
        .offset(skip)
        .limit(limit if include_total else limit + 1)
    )
    loaded_reps = list(result.scalars().all())
    reps = loaded_reps[:limit]
    has_more = (
        skip + len(reps) < total
        if total is not None
        else len(loaded_reps) > limit
    )
    if total is not None:
        response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Page-Size"] = str(len(reps))
    linked = await _linked_ids(db, [r.id for r in reps])
    return [_with_has_user(r, linked) for r in reps]


@router.post("", response_model=RepresentativeRead, status_code=status.HTTP_201_CREATED)
async def create_representative(
    payload: RepresentativeCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_roles(UserRole.admin)),
):
    duplicate_email = (
        await db.execute(
            select(Representative.id).where(
                func.lower(Representative.email)
                == str(payload.email).lower()
            ).limit(1)
        )
    ).scalar_one_or_none()
    if duplicate_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um representante com este e-mail.",
        )
    rep = Representative(**payload.model_dump())
    db.add(rep)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um representante com este e-mail.",
        )
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
    if is_client_account(current_user):
        authorized = (
            await db.execute(
                select(Client.id)
                .where(
                    Client.id == current_user.linked_id,
                    Client.rep_id == rep_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not authorized:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado a este representante.",
            )
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
    new_email = update_data.get("email")
    if new_email:
        duplicate_email = (
            await db.execute(
                select(Representative.id).where(
                    func.lower(Representative.email)
                    == str(new_email).lower(),
                    Representative.id != rep.id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um representante com este e-mail.",
            )
    for field, value in update_data.items():
        setattr(rep, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um representante com este e-mail.",
        )
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
