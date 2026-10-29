import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class OrderEmailDocumentRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    sha256: str | None = None
    size_bytes: int | None = None
    generated_at: datetime | None = None


class OrderEmailDeliveryRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    recipient_roles: list[str]
    recipient_email: str | None = None
    status: str
    attempts: int
    created_at: datetime
    updated_at: datetime
    first_attempt_at: datetime | None = None
    next_attempt_at: datetime | None = None
    accepted_at: datetime | None = None
    delivered_at: datetime | None = None
    last_event_type: str | None = None
    last_event_at: datetime | None = None
    last_error: str | None = None
    origin: str
    resend_of_id: uuid.UUID | None = None
    can_resend: bool = False


class OrderEmailHistoryRead(BaseModel):
    document: OrderEmailDocumentRead | None = None
    deliveries: list[OrderEmailDeliveryRead]
    test_send_available: bool = False


class OrderEmailResendRequest(BaseModel):
    delivery_id: uuid.UUID
    use_current_address: bool = False


class OrderEmailTestSendRequest(BaseModel):
    recipient_email: EmailStr
