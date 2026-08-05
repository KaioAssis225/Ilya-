import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_roles
from app.core.limiter import limiter
from app.core.privacy_audit import record_privacy_event
from app.core.security import verify_password
from app.models.client import Client
from app.models.integration_outbox import IntegrationOutbox
from app.models.notification import Notification
from app.models.order import Order
from app.models.privacy_event import PrivacyEvent
from app.models.privacy_incident import PrivacyIncident
from app.models.refresh_token import RefreshToken
from app.models.representative import Representative
from app.models.retention import LegalHold, RetentionReview
from app.models.signature_invitation import SignatureInvitation
from app.models.user import User, UserRole
from app.schemas.retention import (
    LegalHoldCreate,
    LegalHoldRead,
    LegalHoldRelease,
    RetentionApprovalRequest,
    RetentionDryRunRequest,
    RetentionReviewRead,
    RepresentativeRelationshipEndRead,
    RepresentativeRelationshipEndRequest,
    PrivacyIncidentCreate,
    PrivacyIncidentRead,
    PrivacyIncidentUpdate,
)

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])
_ADMIN = Depends(require_roles(UserRole.admin))

_POLICY_VERSION = "2026-08-05-v3"
_MAX_SNAPSHOT_CANDIDATES = 5_000


def _add_calendar_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _is_active_hold(now: datetime):
    return (
        LegalHold.released_at.is_(None)
        & or_(LegalHold.expires_at.is_(None), LegalHold.expires_at > now)
    )


def _hold_exists(subject_type: str, subject_id, now: datetime):
    return exists(
        select(LegalHold.id).where(
            LegalHold.subject_type == subject_type,
            LegalHold.subject_id == subject_id,
            _is_active_hold(now),
        )
    )


def _order_hold_exists(now: datetime):
    direct = _hold_exists("order", Order.id, now)
    client = _hold_exists("client", Order.client_id, now)
    representative = _hold_exists("representative", Order.rep_id, now)
    return or_(direct, client, representative)


def _notification_hold_exists(now: datetime):
    return exists(
        select(User.id).where(
            User.id == Notification.user_id,
            or_(
                _hold_exists("client", User.linked_id, now),
                _hold_exists("representative", User.rep_id, now),
            ),
        )
    )


def _signature_invitation_hold_exists(now: datetime):
    return or_(
        _hold_exists("order", SignatureInvitation.order_id, now),
        _hold_exists("client", SignatureInvitation.client_id, now),
    )


def _privacy_event_hold_exists(now: datetime):
    return or_(
        (
            (PrivacyEvent.subject_type == "client")
            & _hold_exists("client", PrivacyEvent.subject_id, now)
        ),
        (
            (PrivacyEvent.subject_type == "representative")
            & _hold_exists(
                "representative",
                PrivacyEvent.subject_id,
                now,
            )
        ),
        (
            (PrivacyEvent.subject_type == "order")
            & _hold_exists("order", PrivacyEvent.subject_id, now)
        ),
    )


async def _subject_exists(
    db: AsyncSession,
    subject_type: str,
    subject_id: uuid.UUID,
) -> bool:
    model = {
        "client": Client,
        "representative": Representative,
        "order": Order,
    }[subject_type]
    return (
        await db.execute(select(model.id).where(model.id == subject_id))
    ).scalar_one_or_none() is not None


def _hold_read(hold: LegalHold, now: datetime) -> LegalHoldRead:
    active = (
        hold.released_at is None
        and (hold.expires_at is None or hold.expires_at > now)
    )
    return LegalHoldRead(
        id=hold.id,
        subject_type=hold.subject_type,
        subject_id=hold.subject_id,
        reason=hold.reason,
        expires_at=hold.expires_at,
        released_at=hold.released_at,
        release_reason=hold.release_reason,
        created_at=hold.created_at,
        active=active,
    )


@router.get("/legal-holds", response_model=list[LegalHoldRead])
async def list_legal_holds(
    active_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    now = datetime.now(timezone.utc)
    stmt = select(LegalHold).order_by(LegalHold.created_at.desc()).limit(limit)
    if active_only:
        stmt = stmt.where(_is_active_hold(now))
    holds = (await db.execute(stmt)).scalars().all()
    return [_hold_read(hold, now) for hold in holds]


@router.post(
    "/legal-holds",
    response_model=LegalHoldRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/hour")
async def create_legal_hold(
    payload: LegalHoldCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    now = datetime.now(timezone.utc)
    if payload.expires_at is not None and payload.expires_at <= now:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A expiração precisa estar no futuro.",
        )
    if not await _subject_exists(db, payload.subject_type, payload.subject_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro não encontrado.")
    duplicate = (
        await db.execute(
            select(LegalHold.id).where(
                LegalHold.subject_type == payload.subject_type,
                LegalHold.subject_id == payload.subject_id,
                _is_active_hold(now),
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Já existe um legal hold ativo para este registro.",
        )

    hold = LegalHold(
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        reason=payload.reason,
        expires_at=payload.expires_at,
        created_by_user_id=current_user.id,
    )
    db.add(hold)
    await db.flush()
    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        action="legal_hold_created",
        request=request,
        legal_basis="LGPD Art. 16",
        context={"legal_hold_id": str(hold.id)},
    )
    await db.commit()
    await db.refresh(hold)
    return _hold_read(hold, now)


@router.post(
    "/legal-holds/{hold_id}/release",
    response_model=LegalHoldRead,
)
@limiter.limit("10/hour")
async def release_legal_hold(
    hold_id: uuid.UUID,
    payload: LegalHoldRelease,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha incorreta.")
    hold = (
        await db.execute(
            select(LegalHold).where(LegalHold.id == hold_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not hold:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Legal hold não encontrado.")
    if hold.released_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Legal hold já foi liberado.",
        )
    now = datetime.now(timezone.utc)
    hold.released_at = now
    hold.released_by_user_id = current_user.id
    hold.release_reason = payload.reason
    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type=hold.subject_type,
        subject_id=hold.subject_id,
        action="legal_hold_released",
        request=request,
        legal_basis="LGPD Art. 16",
        context={"legal_hold_id": str(hold.id)},
    )
    await db.commit()
    await db.refresh(hold)
    return _hold_read(hold, now)


async def _count(db: AsyncSession, model, condition) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(model).where(condition)
            )
        ).scalar_one()
    )


async def _candidate_rows(
    db: AsyncSession,
    model,
    condition,
    reference_column,
    remaining: int,
):
    if remaining <= 0:
        return []
    return (
        await db.execute(
            select(model.id, reference_column.label("reference_at"))
            .where(condition)
            .order_by(reference_column, model.id)
            .limit(remaining)
        )
    ).all()


@router.get("/incidents", response_model=list[PrivacyIncidentRead])
async def list_privacy_incidents(
    incident_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(investigating|contained|closed)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    stmt = select(PrivacyIncident).order_by(
        PrivacyIncident.known_at.desc(),
        PrivacyIncident.id.desc(),
    ).limit(limit)
    if incident_status is not None:
        stmt = stmt.where(PrivacyIncident.status == incident_status)
    return (await db.execute(stmt)).scalars().all()


@router.post(
    "/incidents",
    response_model=PrivacyIncidentRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/hour")
async def create_privacy_incident(
    payload: PrivacyIncidentCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    now = datetime.now(timezone.utc)
    if payload.known_at > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A data de ciência não pode estar no futuro.",
        )
    incident = PrivacyIncident(
        **payload.model_dump(),
        retain_until=_add_calendar_years(now, 5),
        created_at=now,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(incident)
    await db.flush()
    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="privacy_incident",
        subject_id=incident.id,
        action="privacy_incident_created",
        request=request,
        legal_basis="LGPD Art. 48 e Resolução CD/ANPD 15/2024",
        context={
            "status": incident.status,
            "retain_until": incident.retain_until.isoformat(),
            "anpd_notified": incident.anpd_notified,
            "subjects_notified": incident.subjects_notified,
        },
    )
    await db.commit()
    await db.refresh(incident)
    return incident


@router.patch(
    "/incidents/{incident_id}",
    response_model=PrivacyIncidentRead,
)
@limiter.limit("30/hour")
async def update_privacy_incident(
    incident_id: uuid.UUID,
    payload: PrivacyIncidentUpdate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    incident = (
        await db.execute(
            select(PrivacyIncident)
            .where(PrivacyIncident.id == incident_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incidente não encontrado.")

    update_data = payload.model_dump(
        exclude_unset=True,
    )
    target_anpd = update_data.get("anpd_notified", incident.anpd_notified)
    target_subjects = update_data.get(
        "subjects_notified",
        incident.subjects_notified,
    )
    target_details = update_data.get(
        "notification_details",
        incident.notification_details,
    )
    target_reason = update_data.get(
        "non_notification_reason",
        incident.non_notification_reason,
    )
    if (target_anpd or target_subjects) and not target_details:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe os detalhes das comunicações realizadas.",
        )
    if not target_anpd and not target_subjects and not target_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fundamente a decisão de ainda não comunicar.",
        )
    target_status = update_data.get("status", incident.status)
    target_root_cause = update_data.get("root_cause", incident.root_cause)
    target_actions = update_data.get(
        "corrective_actions",
        incident.corrective_actions,
    )
    if target_status == "closed" and (
        not target_root_cause or not target_actions
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Para encerrar, registre a causa raiz e as ações corretivas."
            ),
        )

    previous_status = incident.status
    for field, value in update_data.items():
        setattr(incident, field, value)
    if incident.status == "closed" and incident.closed_at is None:
        incident.closed_at = datetime.now(timezone.utc)
    elif incident.status != "closed":
        incident.closed_at = None
    incident.updated_by_user_id = current_user.id

    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="privacy_incident",
        subject_id=incident.id,
        action="privacy_incident_updated",
        request=request,
        legal_basis="LGPD Art. 48 e Resolução CD/ANPD 15/2024",
        context={
            "previous_status": previous_status,
            "status": incident.status,
            "changed_fields": sorted(update_data),
        },
    )
    await db.commit()
    await db.refresh(incident)
    return incident


@router.post(
    "/representatives/{representative_id}/relationship-end",
    response_model=RepresentativeRelationshipEndRead,
)
@limiter.limit("10/hour")
async def end_representative_relationship(
    representative_id: uuid.UUID,
    payload: RepresentativeRelationshipEndRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    now = datetime.now(timezone.utc)
    if payload.ended_at > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A data de encerramento não pode estar no futuro.",
        )
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Senha inválida.",
        )
    representative = (
        await db.execute(
            select(Representative)
            .where(Representative.id == representative_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if representative is None:
        raise HTTPException(status_code=404, detail="Representante não encontrado.")

    previous_end = representative.relationship_ended_at
    representative.relationship_ended_at = payload.ended_at
    linked_users = (
        await db.execute(
            select(User).where(
                User.role == UserRole.representante,
                or_(
                    User.rep_id == representative_id,
                    User.linked_id == representative_id,
                ),
                User.is_active.is_(True),
            )
        )
    ).scalars().all()
    user_ids: list[uuid.UUID] = []
    for user in linked_users:
        user.is_active = False
        user.auth_version += 1
        user_ids.append(user.id)
    if user_ids:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id.in_(user_ids),
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=now)
        )

    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="representative",
        subject_id=representative.id,
        action="representative_relationship_ended",
        request=request,
        legal_basis="LGPD Arts. 15 e 16",
        context={
            "ended_at": payload.ended_at.isoformat(),
            "previous_end": (
                previous_end.isoformat() if previous_end is not None else None
            ),
            "reason": payload.reason,
            "deactivated_users": len(user_ids),
        },
    )
    await db.commit()
    return RepresentativeRelationshipEndRead(
        representative_id=representative.id,
        relationship_ended_at=payload.ended_at,
        deactivated_users=len(user_ids),
    )


@router.post(
    "/retention-reviews/dry-run",
    response_model=RetentionReviewRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def create_retention_dry_run(
    payload: RetentionDryRunRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    """Cria uma fotografia não destrutiva; não existe execução nesta API."""
    now = datetime.now(timezone.utc)
    cutoffs = {
        "clients": now - timedelta(days=730),
        "open_orders": now - timedelta(days=730),
        "closed_orders": now - timedelta(days=3650),
        "representatives": now - timedelta(days=1825),
        "notifications_read": now - timedelta(days=90),
        "notifications_unread": now - timedelta(days=365),
        "signature_invitations": now - timedelta(days=30),
        "outbox_delivered": now - timedelta(days=90),
        "privacy_events": now - timedelta(days=1825),
    }
    summary: dict = {}
    candidates: list[dict] = []
    total_candidates = 0

    if "clients" in payload.categories:
        due = (
            (Client.last_activity_at < cutoffs["clients"])
            & ~exists(select(Order.id).where(Order.client_id == Client.id))
            & ~exists(
                select(User.id).where(
                    User.linked_id == Client.id,
                    User.is_active.is_(True),
                )
            )
        )
        held = due & _hold_exists("client", Client.id, now)
        eligible = due & ~_hold_exists("client", Client.id, now)
        due_count = await _count(db, Client, due)
        held_count = await _count(db, Client, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["clients"] = {
            "status": "evaluated",
            "retention_days": 730,
            "reference_field": "last_activity_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "delete_if_still_unlinked",
        }
        for row in await _candidate_rows(
            db,
            Client,
            eligible,
            Client.last_activity_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "client",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "delete_if_still_unlinked",
                }
            )

    order_hold = _order_hold_exists(now)
    if "open_orders" in payload.categories:
        due = (
            (Order.updated_at < cutoffs["open_orders"])
            & Order.is_finalized.is_(False)
            & Order.is_cancelled.is_(False)
        )
        held = due & order_hold
        eligible = due & ~order_hold
        due_count = await _count(db, Order, due)
        held_count = await _count(db, Order, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["open_orders"] = {
            "status": "evaluated",
            "retention_days": 730,
            "reference_field": "updated_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "manual_review",
        }
        for row in await _candidate_rows(
            db,
            Order,
            eligible,
            Order.updated_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "order",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "manual_review",
                    "category": "open_orders",
                }
            )

    if "closed_orders" in payload.categories:
        closed_at = func.coalesce(Order.finalized_at, Order.cancelled_at)
        due = (
            (closed_at < cutoffs["closed_orders"])
            & or_(
                Order.is_finalized.is_(True),
                Order.is_cancelled.is_(True),
            )
        )
        held = due & order_hold
        eligible = due & ~order_hold
        due_count = await _count(db, Order, due)
        held_count = await _count(db, Order, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["closed_orders"] = {
            "status": "evaluated",
            "retention_days": 3650,
            "reference_field": "finalized_at/cancelled_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "anonymize_after_manual_review",
        }
        for row in await _candidate_rows(
            db,
            Order,
            eligible,
            closed_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "order",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "anonymize_after_manual_review",
                    "category": "closed_orders",
                }
            )

    if "representatives" in payload.categories:
        due = (
            Representative.relationship_ended_at
            < cutoffs["representatives"]
        )
        held = due & _hold_exists(
            "representative",
            Representative.id,
            now,
        )
        eligible = due & ~_hold_exists(
            "representative",
            Representative.id,
            now,
        )
        due_count = await _count(db, Representative, due)
        held_count = await _count(db, Representative, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["representatives"] = {
            "status": "evaluated",
            "retention_years_after_end": 5,
            "reference_field": "relationship_ended_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "anonymize_after_manual_review",
        }
        for row in await _candidate_rows(
            db,
            Representative,
            eligible,
            Representative.relationship_ended_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "representative",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "anonymize_after_manual_review",
                    "category": "representatives",
                }
            )

    notification_hold = _notification_hold_exists(now)
    if "notifications_read" in payload.categories:
        due = (
            Notification.is_read.is_(True)
            & (Notification.read_at < cutoffs["notifications_read"])
        )
        held = due & notification_hold
        eligible = due & ~notification_hold
        due_count = await _count(db, Notification, due)
        held_count = await _count(db, Notification, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["notifications_read"] = {
            "status": "evaluated",
            "retention_days": 90,
            "reference_field": "read_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "delete_after_manual_review",
        }
        for row in await _candidate_rows(
            db,
            Notification,
            eligible,
            Notification.read_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "notification",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "delete_after_manual_review",
                    "category": "notifications_read",
                }
            )

    if "notifications_unread" in payload.categories:
        due = (
            Notification.is_read.is_(False)
            & (Notification.created_at < cutoffs["notifications_unread"])
        )
        held = due & notification_hold
        eligible = due & ~notification_hold
        due_count = await _count(db, Notification, due)
        held_count = await _count(db, Notification, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["notifications_unread"] = {
            "status": "evaluated",
            "retention_days": 365,
            "reference_field": "created_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "delete_after_manual_review",
        }
        for row in await _candidate_rows(
            db,
            Notification,
            eligible,
            Notification.created_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "notification",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "delete_after_manual_review",
                    "category": "notifications_unread",
                }
            )

    if "signature_invitations" in payload.categories:
        invitation_terminal_at = func.greatest(
            SignatureInvitation.expires_at,
            func.coalesce(
                SignatureInvitation.consumed_at,
                SignatureInvitation.expires_at,
            ),
            func.coalesce(
                SignatureInvitation.revoked_at,
                SignatureInvitation.expires_at,
            ),
        )
        due = invitation_terminal_at < cutoffs["signature_invitations"]
        invitation_hold = _signature_invitation_hold_exists(now)
        held = due & invitation_hold
        eligible = due & ~invitation_hold
        due_count = await _count(db, SignatureInvitation, due)
        held_count = await _count(db, SignatureInvitation, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["signature_invitations"] = {
            "status": "evaluated",
            "retention_days": 30,
            "reference_field": "expires_at/consumed_at/revoked_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "delete_token_metadata_after_review",
        }
        for row in await _candidate_rows(
            db,
            SignatureInvitation,
            eligible,
            invitation_terminal_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "signature_invitation",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "delete_token_metadata_after_review",
                    "category": "signature_invitations",
                }
            )

    if "outbox_delivered" in payload.categories:
        due = (
            (IntegrationOutbox.status == "delivered")
            & (
                IntegrationOutbox.delivered_at
                < cutoffs["outbox_delivered"]
            )
        )
        due_count = await _count(db, IntegrationOutbox, due)
        total_candidates += due_count
        summary["outbox_delivered"] = {
            "status": "evaluated",
            "retention_days": 90,
            "reference_field": "delivered_at",
            "due": due_count,
            "blocked_by_legal_hold": 0,
            "candidates": due_count,
            "proposed_action": "delete_payload_preserve_metrics",
        }
        for row in await _candidate_rows(
            db,
            IntegrationOutbox,
            due,
            IntegrationOutbox.delivered_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "integration_outbox",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "delete_payload_preserve_metrics",
                    "category": "outbox_delivered",
                }
            )

    if "outbox_dead_letter" in payload.categories:
        due = IntegrationOutbox.status == "dead_letter"
        due_count = await _count(db, IntegrationOutbox, due)
        total_candidates += due_count
        summary["outbox_dead_letter"] = {
            "status": "evaluated",
            "reference_field": "dead_lettered_at",
            "due": due_count,
            "blocked_by_legal_hold": 0,
            "candidates": due_count,
            "proposed_action": "resolve_manually_never_auto_delete",
        }
        for row in await _candidate_rows(
            db,
            IntegrationOutbox,
            due,
            IntegrationOutbox.dead_lettered_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "integration_outbox",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "resolve_manually_never_auto_delete",
                    "category": "outbox_dead_letter",
                }
            )

    if "privacy_events" in payload.categories:
        due = PrivacyEvent.created_at < cutoffs["privacy_events"]
        event_hold = _privacy_event_hold_exists(now)
        held = due & event_hold
        eligible = due & ~event_hold
        due_count = await _count(db, PrivacyEvent, due)
        held_count = await _count(db, PrivacyEvent, held)
        candidate_count = due_count - held_count
        total_candidates += candidate_count
        summary["privacy_events"] = {
            "status": "evaluated",
            "retention_days": 1825,
            "reference_field": "created_at",
            "due": due_count,
            "blocked_by_legal_hold": held_count,
            "candidates": candidate_count,
            "proposed_action": "manual_review_before_minimization",
        }
        for row in await _candidate_rows(
            db,
            PrivacyEvent,
            eligible,
            PrivacyEvent.created_at,
            _MAX_SNAPSHOT_CANDIDATES - len(candidates),
        ):
            candidates.append(
                {
                    "subject_type": "privacy_event",
                    "subject_id": str(row.id),
                    "reference_at": row.reference_at.isoformat(),
                    "proposed_action": "manual_review_before_minimization",
                    "category": "privacy_events",
                }
            )

    review = RetentionReview(
        policy_version=_POLICY_VERSION,
        evaluated_at=now,
        candidate_count=total_candidates,
        truncated=(
            total_candidates > _MAX_SNAPSHOT_CANDIDATES
            or len(candidates) != total_candidates
        ),
        summary=summary,
        candidates=candidates,
        created_by_user_id=current_user.id,
    )
    db.add(review)
    await db.flush()
    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="retention_review",
        subject_id=review.id,
        action="retention_dry_run_created",
        request=request,
        legal_basis="LGPD Arts. 15 e 16",
        context={
            "candidate_count": total_candidates,
            "truncated": review.truncated,
            "policy_version": _POLICY_VERSION,
        },
    )
    await db.commit()
    await db.refresh(review)
    return RetentionReviewRead.model_validate(
        review,
        from_attributes=True,
    )


@router.get(
    "/retention-reviews",
    response_model=list[RetentionReviewRead],
)
async def list_retention_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    _: User = _ADMIN,
):
    reviews = (
        await db.execute(
            select(RetentionReview)
            .order_by(RetentionReview.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        RetentionReviewRead.model_validate(item, from_attributes=True)
        for item in reviews
    ]


@router.post(
    "/retention-reviews/{review_id}/approve",
    response_model=RetentionReviewRead,
)
@limiter.limit("10/hour")
async def approve_retention_review(
    review_id: uuid.UUID,
    payload: RetentionApprovalRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
):
    """Aprova somente o relatório; não autoriza nem executa descarte."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha incorreta.")
    review = (
        await db.execute(
            select(RetentionReview)
            .where(RetentionReview.id == review_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not review:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relatório não encontrado.")
    if review.status != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Relatório já foi aprovado.",
        )
    if review.truncated:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Relatório truncado não pode ser aprovado.",
        )
    review.status = "approved"
    review.approved_by_user_id = current_user.id
    review.approved_at = datetime.now(timezone.utc)
    record_privacy_event(
        db,
        actor_user_id=current_user.id,
        subject_type="retention_review",
        subject_id=review.id,
        action="retention_review_approved",
        request=request,
        legal_basis="LGPD Arts. 15 e 16",
        context={
            "candidate_count": review.candidate_count,
            "execution_enabled": False,
        },
    )
    await db.commit()
    await db.refresh(review)
    return RetentionReviewRead.model_validate(
        review,
        from_attributes=True,
    )
