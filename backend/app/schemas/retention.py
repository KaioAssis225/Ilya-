import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
