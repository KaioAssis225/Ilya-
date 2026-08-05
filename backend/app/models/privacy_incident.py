import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PrivacyIncident(Base, TimestampMixin):
    __tablename__ = "privacy_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    known_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="investigating",
        server_default="investigating",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    data_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    affected_subjects_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    risk_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation_measures: Mapped[str] = mapped_column(Text, nullable=False)
    anpd_notified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    subjects_notified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    notification_details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    non_notification_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retain_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('investigating', 'contained', 'closed')",
            name="ck_privacy_incidents_status",
        ),
        CheckConstraint(
            "affected_subjects_count IS NULL OR affected_subjects_count >= 0",
            name="ck_privacy_incidents_affected_count",
        ),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name="ck_privacy_incidents_closed_timestamp",
        ),
        CheckConstraint(
            "retain_until >= created_at + INTERVAL '5 years'",
            name="ck_privacy_incidents_minimum_retention",
        ),
        Index("ix_privacy_incidents_known_id", "known_at", "id"),
        Index("ix_privacy_incidents_status_known", "status", "known_at"),
        Index("ix_privacy_incidents_retain_until", "retain_until", "id"),
        Index(
            "ix_privacy_incidents_created_by",
            "created_by_user_id",
        ),
    )
