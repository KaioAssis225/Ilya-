import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


RetentionSubjectType = Literal["client", "representative", "order"]


class LegalHoldCreate(BaseModel):
    subject_type: RetentionSubjectType
    subject_id: uuid.UUID
    reason: str = Field(min_length=5, max_length=2000)
    expires_at: datetime | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 5:
            raise ValueError("Informe um motivo com pelo menos 5 caracteres.")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("A expiração precisa incluir o fuso horário.")
        return value


class LegalHoldRelease(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=5, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 5:
            raise ValueError("Informe um motivo com pelo menos 5 caracteres.")
        return normalized


class LegalHoldRead(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    reason: str
    expires_at: datetime | None
    released_at: datetime | None
    release_reason: str | None
    created_at: datetime
    active: bool


class RetentionDryRunRequest(BaseModel):
    categories: list[
        Literal["clients", "open_orders", "closed_orders", "representatives"]
    ] = Field(
        default_factory=lambda: [
            "clients",
            "open_orders",
            "closed_orders",
            "representatives",
        ],
        min_length=1,
        max_length=4,
    )

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Categorias não podem ser repetidas.")
        return value


class RetentionApprovalRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class RepresentativeRelationshipEndRequest(BaseModel):
    ended_at: datetime
    reason: str = Field(min_length=5, max_length=2000)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("ended_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A data de encerramento precisa incluir o fuso horário.")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 5:
            raise ValueError("Informe um motivo com pelo menos 5 caracteres.")
        return normalized


class RepresentativeRelationshipEndRead(BaseModel):
    representative_id: uuid.UUID
    relationship_ended_at: datetime
    deactivated_users: int


class IncidentEvidenceReference(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=500)

    @field_validator("label", "reference")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A referência não pode ficar vazia.")
        return normalized


class PrivacyIncidentCreate(BaseModel):
    known_at: datetime
    description: str = Field(min_length=10, max_length=5000)
    data_categories: list[str] = Field(min_length=1, max_length=30)
    affected_subjects_count: int | None = Field(default=None, ge=0)
    risk_assessment: str = Field(min_length=10, max_length=5000)
    mitigation_measures: str = Field(min_length=5, max_length=5000)
    anpd_notified: bool = False
    subjects_notified: bool = False
    notification_details: str | None = Field(default=None, max_length=5000)
    non_notification_reason: str | None = Field(default=None, max_length=5000)
    evidence_references: list[IncidentEvidenceReference] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("known_at")
    @classmethod
    def require_known_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A data de ciência precisa incluir o fuso horário.")
        return value

    @field_validator("data_categories")
    @classmethod
    def normalize_categories(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value))
        if any(not item or len(item) > 100 for item in normalized):
            raise ValueError("Categorias devem conter de 1 a 100 caracteres.")
        return normalized

    @field_validator(
        "description",
        "risk_assessment",
        "mitigation_measures",
        "notification_details",
        "non_notification_reason",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        normalized = value.strip() if value is not None else None
        minimums = {
            "description": 10,
            "risk_assessment": 10,
            "mitigation_measures": 5,
        }
        minimum = minimums.get(info.field_name)
        if minimum is not None and (
            normalized is None or len(normalized) < minimum
        ):
            raise ValueError(
                f"O campo deve ter pelo menos {minimum} caracteres úteis."
            )
        return normalized or None

    @model_validator(mode="after")
    def validate_notification_decision(self):
        if (self.anpd_notified or self.subjects_notified) and not self.notification_details:
            raise ValueError("Informe os detalhes das comunicações realizadas.")
        if (
            not self.anpd_notified
            and not self.subjects_notified
            and not self.non_notification_reason
        ):
            raise ValueError("Fundamente a decisão de ainda não comunicar.")
        return self


class PrivacyIncidentUpdate(BaseModel):
    status: Literal["investigating", "contained", "closed"] | None = None
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    data_categories: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )
    affected_subjects_count: int | None = Field(default=None, ge=0)
    risk_assessment: str | None = Field(default=None, min_length=10, max_length=5000)
    mitigation_measures: str | None = Field(default=None, min_length=5, max_length=5000)
    anpd_notified: bool | None = None
    subjects_notified: bool | None = None
    notification_details: str | None = Field(default=None, max_length=5000)
    non_notification_reason: str | None = Field(default=None, max_length=5000)
    evidence_references: list[IncidentEvidenceReference] | None = Field(
        default=None,
        max_length=100,
    )
    root_cause: str | None = Field(default=None, min_length=5, max_length=5000)
    corrective_actions: str | None = Field(default=None, min_length=5, max_length=5000)

    @field_validator("data_categories")
    @classmethod
    def normalize_update_categories(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        return (
            PrivacyIncidentCreate.normalize_categories(value)
            if value is not None
            else None
        )

    @field_validator(
        "description",
        "risk_assessment",
        "mitigation_measures",
        "notification_details",
        "non_notification_reason",
        "root_cause",
        "corrective_actions",
    )
    @classmethod
    def normalize_update_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        normalized = value.strip() if value is not None else None
        minimums = {
            "description": 10,
            "risk_assessment": 10,
            "mitigation_measures": 5,
            "root_cause": 5,
            "corrective_actions": 5,
        }
        minimum = minimums.get(info.field_name)
        if normalized is not None and minimum is not None and len(normalized) < minimum:
            raise ValueError(
                f"O campo deve ter pelo menos {minimum} caracteres úteis."
            )
        return normalized or None


class PrivacyIncidentRead(BaseModel):
    id: uuid.UUID
    known_at: datetime
    status: str
    description: str
    data_categories: list[str]
    affected_subjects_count: int | None
    risk_assessment: str
    mitigation_measures: str
    anpd_notified: bool
    subjects_notified: bool
    notification_details: str | None
    non_notification_reason: str | None
    evidence_references: list[IncidentEvidenceReference]
    root_cause: str | None
    corrective_actions: str | None
    closed_at: datetime | None
    retain_until: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RetentionReviewRead(BaseModel):
    id: uuid.UUID
    status: str
    policy_version: str
    evaluated_at: datetime
    candidate_count: int
    truncated: bool
    summary: dict[str, Any]
    candidates: list[dict[str, Any]]
    approved_at: datetime | None
    created_at: datetime
