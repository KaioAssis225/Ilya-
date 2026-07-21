"""Caixa de saída de eventos de integração (padrão Transactional Outbox).

O evento é gravado na MESMA transação da alteração de negócio. Um worker
separado entrega depois. Assim uma indisponibilidade do sistema receptor nunca
impede o Ilya de finalizar um pedido ou cadastrar um produto — o recado apenas
fica pendente até ser entregue.

Entrega é at-least-once: um evento pode chegar mais de uma vez ao receptor,
mas nunca é perdido em silêncio. A idempotência é responsabilidade do receptor,
via `event_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Estados possíveis de um evento na outbox.
OUTBOX_STATUSES = ("pending", "processing", "delivered", "failed", "dead_letter")


class IntegrationOutbox(Base, TimestampMixin):
    __tablename__ = "integration_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Identificador global do evento — é o que o receptor usa para descartar
    # duplicatas. Único aqui também para impedir enfileiramento duplo.
    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )

    # Envelope completo já pronto para envio (event_id, event_type, source,
    # occurred_at, correlation_id, data). Guardar o envelope montado — e não só
    # o `data` — garante que uma retentativa envie exatamente o mesmo corpo,
    # senão a assinatura HMAC mudaria entre tentativas.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Erro resumido e sanitizado — nunca o corpo completo nem o segredo.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed', 'dead_letter')",
            name="ck_integration_outbox_status",
        ),
        # Índice quente do worker: "o que está pronto para enviar agora?".
        # Parcial de propósito — as linhas `delivered` viram a maioria absoluta
        # da tabela com o tempo e ficariam fora do índice, mantendo-o pequeno.
        Index(
            "ix_integration_outbox_due",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        return (
            f"<IntegrationOutbox {self.event_type} "
            f"status={self.status} attempts={self.attempts}>"
        )
