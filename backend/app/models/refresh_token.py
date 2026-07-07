import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Boolean, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(lazy="selectin")


async def cleanup_expired_tokens(db: AsyncSession) -> None:
    """Remove refresh tokens expirados ou já revogados (Bloco 68, item 7)."""
    now = datetime.now(timezone.utc)
    await db.execute(delete(RefreshToken).where(or_(RefreshToken.expires_at < now, RefreshToken.revoked.is_(True))))
    await db.commit()
