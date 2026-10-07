import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductFiscalAssignmentEvent(Base):
    """Snapshot da classificação fiscal BR escolhida para um produto."""

    __tablename__ = "product_fiscal_assignment_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    market_code: Mapped[str] = mapped_column(ForeignKey("markets.code"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    old_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_group_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    new_group_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    old_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    new_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("market_code = 'BR'", name="ck_product_fiscal_assignment_br_only"),
        CheckConstraint("action IN ('created', 'updated')", name="ck_product_fiscal_assignment_action"),
        CheckConstraint("source IN ('api', 'csv')", name="ck_product_fiscal_assignment_source"),
        Index("ix_product_fiscal_assignment_product_created", "product_id", "created_at"),
        Index("ix_product_fiscal_assignment_actor_created", "actor_user_id", "created_at"),
    )
