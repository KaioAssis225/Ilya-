import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductGroupAuditEvent(Base):
    """Trilha imutável das mudanças que podem alterar o IPI faturado no BR."""

    __tablename__ = "product_group_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Identificador histórico sem FK: a exclusão do grupo não pode apagar nem
    # zerar a referência que explica qual cadastro fiscal foi removido.
    product_group_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    # Também histórico e obrigatório: excluir/desativar a conta não pode apagar
    # quem realizou a mudança fiscal.
    actor_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    market_code: Mapped[str] = mapped_column(
        ForeignKey("markets.code"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    new_ipi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "market_code = 'BR'",
            name="ck_product_group_audit_br_only",
        ),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted')",
            name="ck_product_group_audit_action",
        ),
        CheckConstraint(
            "source IN ('api', 'csv')",
            name="ck_product_group_audit_source",
        ),
        CheckConstraint(
            "(action = 'created' AND old_ipi IS NULL AND new_ipi IS NOT NULL) "
            "OR (action = 'updated' AND old_ipi IS NOT NULL AND new_ipi IS NOT NULL) "
            "OR (action = 'deleted' AND old_ipi IS NOT NULL AND new_ipi IS NULL)",
            name="ck_product_group_audit_values",
        ),
        Index(
            "ix_product_group_audit_group_created",
            "product_group_id",
            "created_at",
        ),
        Index(
            "ix_product_group_audit_actor_created",
            "actor_user_id",
            "created_at",
        ),
        Index(
            "ix_product_group_audit_market_created",
            "market_code",
            "created_at",
        ),
    )
