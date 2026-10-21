import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.retention import LegalHold


def is_active_hold(now: datetime):
    return (
        LegalHold.released_at.is_(None)
        & or_(LegalHold.expires_at.is_(None), LegalHold.expires_at > now)
    )


def hold_exists(subject_type: str, subject_id, now: datetime):
    return exists(
        select(LegalHold.id).where(
            LegalHold.subject_type == subject_type,
            LegalHold.subject_id == subject_id,
            is_active_hold(now),
        )
    )


async def ensure_no_active_legal_hold(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
) -> None:
    """LGPD Art. 16: retenção legal ativa suspende exclusão e anonimização.

    Vale para o próprio cadastro e para pedidos vinculados a ele — apagar ou
    anonimizar o titular de um pedido retido destrói a prova que a retenção
    protege. Responde 409 sem alterar nada.
    """
    now = datetime.now(timezone.utc)
    order_owner = Order.client_id if subject_type == "client" else Order.rep_id
    held = (
        await db.execute(
            select(
                hold_exists(subject_type, subject_id, now)
                | exists(
                    select(Order.id).where(
                        order_owner == subject_id,
                        hold_exists("order", Order.id, now),
                    )
                )
            )
        )
    ).scalar()
    if held:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este cadastro está sob retenção legal ativa e não pode ser "
                "excluído nem anonimizado enquanto ela durar."
            ),
        )
