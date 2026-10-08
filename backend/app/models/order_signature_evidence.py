import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderSignatureEvidence(Base):
    """Atestado de assinatura; legado sem prova permanece explicitamente inconclusivo."""

    __tablename__ = "order_signature_evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    signer_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="1")
    signature_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signature_invitations.id", ondelete="SET NULL"), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "signer_kind", name="uq_order_signature_evidence_signer"),
        Index("ix_order_signature_evidence_order_id", "order_id"),
    )
