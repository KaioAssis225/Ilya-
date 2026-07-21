"""Schemas dos endpoints administrativos de integração (Outbox)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TestEventRequest(BaseModel):
    """Corpo opcional para disparar um evento de teste."""

    # Texto livre só para reconhecer o evento no receptor durante a prova da
    # estrada. Nada aqui vira regra de negócio.
    note: str | None = Field(default=None, max_length=200)


class OutboxEventRead(BaseModel):
    """Uma linha da outbox, para inspeção administrativa."""

    id: uuid.UUID
    event_id: uuid.UUID
    event_type: str
    status: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OutboxStatusResponse(BaseModel):
    """Contagem de eventos por status + amostra das últimas linhas."""

    counts: dict[str, int]
    total: int
    recent: list[OutboxEventRead]
