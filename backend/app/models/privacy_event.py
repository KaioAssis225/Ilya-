import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PrivacyEvent(Base):
    """Trilha mínima e persistente das operações relacionadas aos titulares.

    O conteúdo exportado, senhas, tokens, endereços e demais dados pessoais não
    devem ser copiados para esta tabela.
    """

    __tablename__ = "privacy_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
        server_default="completed",
    )
    legal_basis: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_privacy_events_created_id", "created_at", "id"),
        Index("ix_privacy_events_subject", "subject_type", "subject_id"),
        Index("ix_privacy_events_actor_user_id", "actor_user_id"),
        Index("ix_privacy_events_action_created", "action", "created_at"),
    )
