import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy_event import PrivacyEvent


def request_correlation_id(request: Request) -> str | None:
    """Retorna apenas o identificador técnico validado pelo middleware."""
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and len(value) <= 64 else None


def record_privacy_event(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    subject_type: str,
    subject_id: uuid.UUID | None,
    action: str,
    request: Request,
    legal_basis: str | None = None,
    context: dict[str, Any] | None = None,
) -> PrivacyEvent:
    """Inclui um evento na transação corrente sem armazenar conteúdo pessoal."""
    event = PrivacyEvent(
        actor_user_id=actor_user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        action=action,
        outcome="completed",
        legal_basis=legal_basis,
        request_id=request_correlation_id(request),
        context=context,
    )
    db.add(event)
    return event
