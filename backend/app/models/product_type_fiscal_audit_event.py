import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductTypeFiscalAuditEvent(Base):
    """Histórico dos vínculos entre tipo BR e grupo que determina seu IPI."""

    __tablename__ = "product_type_fiscal_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_type_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    old_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_group_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    new_group_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    old_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    new_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("market_code = 'BR'", name="ck_type_fiscal_audit_br_only"),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted')",
            name="ck_type_fiscal_audit_action",
        ),
        CheckConstraint("source IN ('api', 'csv')", name="ck_type_fiscal_audit_source"),
        Index("ix_type_fiscal_audit_type_created", "product_type_id", "created_at"),
        Index("ix_type_fiscal_audit_actor_created", "actor_user_id", "created_at"),
    )
