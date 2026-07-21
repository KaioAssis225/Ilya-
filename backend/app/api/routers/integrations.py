"""Endpoints administrativos da integração Ilya -> Ilya Estoque (Outbox).

Duas operações, ambas restritas a admin:

* disparar um evento de teste (`test.ping`) para provar a estrada ponta a ponta;
* consultar o estado da outbox (contagem por status e últimas linhas).

Nenhum evento de negócio é emitido aqui. O `test.ping` existe só para exercitar
assinatura, entrega e idempotência sem depender de um pedido ou produto real.
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_roles
from app.core.limiter import limiter
from app.models.integration_outbox import OUTBOX_STATUSES, IntegrationOutbox
from app.models.user import User, UserRole
from app.schemas.integration import (
    OutboxStatusResponse,
    TestEventRequest,
)
from app.services.integration_events import enqueue_event

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

_ADMIN = Depends(require_roles(UserRole.admin))

# Amostra de linhas recentes devolvida pela consulta de status.
_RECENT_LIMIT = 20


@router.post("/test-event", response_model=OutboxStatusResponse, status_code=202)
@limiter.limit("10/minute")
async def enqueue_test_event(
    request: Request,
    response: Response,
    payload: TestEventRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
) -> OutboxStatusResponse:
    """Enfileira um evento `test.ping` na outbox.

    O worker (se `WEBHOOK_ENABLED=true`) o entregará; caso contrário ele fica
    `pending`, o que já prova a gravação transacional.
    """
    note = payload.note if payload else None
    await enqueue_event(
        db,
        "test.ping",
        {"note": note, "triggered_by": str(current_user.id)},
    )
    await db.commit()
    return await _build_status(db)


@router.get("/outbox/status", response_model=OutboxStatusResponse)
@limiter.limit("30/minute")
async def get_outbox_status(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = _ADMIN,
) -> OutboxStatusResponse:
    """Contagem de eventos por status e as últimas linhas da outbox."""
    return await _build_status(db)


async def _build_status(db: AsyncSession) -> OutboxStatusResponse:
    count_rows = await db.execute(
        select(IntegrationOutbox.status, func.count())
        .group_by(IntegrationOutbox.status)
    )
    # Começa em zero para todos os status possíveis: o painel fica estável
    # mesmo quando um estado ainda não tem nenhuma linha.
    counts = {status: 0 for status in OUTBOX_STATUSES}
    for status, total in count_rows.all():
        counts[status] = total

    recent_rows = await db.execute(
        select(IntegrationOutbox)
        .order_by(IntegrationOutbox.created_at.desc())
        .limit(_RECENT_LIMIT)
    )
    recent = list(recent_rows.scalars().all())

    return OutboxStatusResponse(
        counts=counts,
        total=sum(counts.values()),
        recent=recent,
    )
