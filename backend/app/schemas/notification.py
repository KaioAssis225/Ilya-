import uuid
from pydantic import BaseModel
from datetime import datetime


class NotificationRead(BaseModel):
    id: uuid.UUID
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
