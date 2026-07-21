"""Montagem e enfileiramento de eventos de integração (Outbox).

O envelope segue a seção 7 do PLANEJAMENTO-WEBHOOK-ILYA-ESTOQUE. A regra de
ouro deste módulo: `enqueue_event` NÃO faz commit. Ele grava na sessão do
chamador para que o evento entre na MESMA transação da alteração de negócio.
Se o pedido não for salvo, o evento também não é — e vice-versa. É isso que
impede o sistema de anunciar um pedido que não existe.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration_outbox import IntegrationOutbox

EVENT_SOURCE = "ilya"


def utc_now_iso() -> str:
    """Instante atual em UTC, ISO-8601 com sufixo Z (formato do contrato)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(
    event_type: str,
    data: dict[str, Any],
    *,
    event_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    event_version: int = 1,
) -> dict[str, Any]:
    """Monta o envelope padrão de um evento."""
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "source": EVENT_SOURCE,
        "occurred_at": utc_now_iso(),
        "correlation_id": str(correlation_id) if correlation_id else None,
        "data": data,
    }


def serialize_envelope(envelope: dict[str, Any]) -> bytes:
    """Serializa o envelope de forma DETERMINÍSTICA.

    `sort_keys` e separadores fixos garantem que a mesma linha da outbox
    produza sempre os mesmos bytes — inclusive entre tentativas. Sem isso,
    duas retentativas gerariam corpos diferentes e depurar uma assinatura
    recusada viraria adivinhação. `ensure_ascii=False` preserva acentuação
    sem escapes, e o corpo trafega em UTF-8.
    """
    return json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


async def enqueue_event(
    session: AsyncSession,
    event_type: str,
    data: dict[str, Any],
    *,
    correlation_id: uuid.UUID | None = None,
    event_version: int = 1,
) -> IntegrationOutbox:
    """Grava um evento na outbox usando a sessão (e transação) do chamador.

    Não chama commit de propósito: quem controla a transação é o caso de uso
    de negócio.
    """
    event_id = uuid.uuid4()
    envelope = build_envelope(
        event_type,
        data,
        event_id=event_id,
        correlation_id=correlation_id,
        event_version=event_version,
    )
    row = IntegrationOutbox(
        event_id=event_id,
        event_type=event_type,
        event_version=event_version,
        payload=envelope,
        correlation_id=correlation_id,
    )
    session.add(row)
    return row
