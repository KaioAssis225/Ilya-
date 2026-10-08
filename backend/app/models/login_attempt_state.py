from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoginAttemptState(Base):
    """Contenção de senha por origem e identificador, sem guardar PII."""

    __tablename__ = "login_attempt_states"

    identifier_fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    origin_fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_login_attempt_states_last_failed_at", "last_failed_at"),
        Index("ix_login_attempt_states_identifier", "identifier_fingerprint"),
    )
