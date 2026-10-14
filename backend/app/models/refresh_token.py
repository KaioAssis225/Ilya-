import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import CheckConstraint, String, ForeignKey, DateTime, Boolean, func, delete, Index, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


_CLEANUP_LOCK_ID = 4_956_921_201


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # R2a: scope separa sessões de mercado (active_market obrigatório) das de
    # plataforma (active_market NULL). Antigos tokens ficam scope='market'.
    # active_market perde server_default='BR': novos tokens devem informar
    # explicitamente o mercado (market) ou omitir (platform).
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="market", server_default="market")
    active_market: Mapped[str | None] = mapped_column(ForeignKey("markets.code"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, index=True, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_refresh_tokens_parent_id", "parent_id"),
        Index(
            "ix_refresh_tokens_active_user_created",
            "user_id",
            "created_at",
            postgresql_where=text("revoked = false"),
        ),
        CheckConstraint(
            "(scope = 'market' AND active_market IS NOT NULL)"
            " OR (scope = 'platform' AND active_market IS NULL)",
            name="ck_refresh_tokens_scope_market",
        ),
        CheckConstraint(
            "scope IN ('market', 'platform')",
            name="ck_refresh_tokens_scope_values",
        ),
    )


async def cleanup_expired_tokens(db: AsyncSession, retention_days: int = 30) -> None:
    """Descarta tokens antigos uma única vez, mesmo com vários workers."""
    acquired = (
        await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": _CLEANUP_LOCK_ID},
        )
    ).scalar()
    if not acquired:
        await db.rollback()
        return
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=retention_days)
    ).replace(tzinfo=None)
    await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < cutoff))
    await db.commit()
