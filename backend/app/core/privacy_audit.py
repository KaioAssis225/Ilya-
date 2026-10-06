import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy_event import PrivacyEvent


def request_correlation_id(request: Request) -> str | None:
    """Retorna apenas o identificador técnico validado pelo middleware."""
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and len(value) <= 64 else None


def session_market(db: AsyncSession) -> str | None:
    """Mercado ativo da sessão, gravado pelo `MarketPrincipal`.

    Uma sessão de plataforma não tem mercado comercial, então o valor é
    legitimamente ausente — operações de privacidade podem ser globais.
    """
    try:
        market = db.sync_session.info.get("active_market")
    except AttributeError:  # sessão sem sync_session (testes com mock)
        return None
    return market if isinstance(market, str) else None


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
    """Inclui um evento na transação corrente sem armazenar conteúdo pessoal.

    O mercado da sessão entra no `context` automaticamente: a trilha precisa
    distinguir o titular BR do titular EU, e deixar isso a cargo de cada chamada
    significaria esquecer em alguma. `market: null` é informação — marca a
    operação como global, feita por sessão de plataforma.
    """
    enriched: dict[str, Any] = {"market": session_market(db)}
    if context:
        # A chamada pode sobrescrever quando conhece o mercado do titular melhor
        # que a sessão — por exemplo, encerramento administrativo de vínculo.
        enriched.update(context)
    event = PrivacyEvent(
        actor_user_id=actor_user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        action=action,
        outcome="completed",
        legal_basis=legal_basis,
        request_id=request_correlation_id(request),
        context=enriched,
    )
    db.add(event)
    return event
