import uuid
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime


class ClientBase(BaseModel):
    name: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=50)
    email: EmailStr
    cep: str = Field(..., max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: str = Field(..., max_length=255)
    city: str = Field(..., max_length=255)
    state: str = Field(..., min_length=2, max_length=2)


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    cep: Optional[str] = Field(None, max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, min_length=2, max_length=2)


class ClientRead(ClientBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    has_user: bool = False

    model_config = {"from_attributes": True}
