import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, Literal
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
    price_profile: Literal["lojista", "corporativo"] = "lojista"
    max_discount: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("UF deve ser informada como texto.")
        state = value.strip().upper()
        if len(state) != 2 or not state.isascii() or not state.isalpha():
            raise ValueError("UF deve conter exatamente 2 letras.")
        return state


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
    price_profile: Optional[Literal["lojista", "corporativo"]] = None
    max_discount: Optional[Decimal] = Field(None, ge=0, le=100)

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("UF deve ser informada como texto.")
        state = value.strip().upper()
        if len(state) != 2 or not state.isascii() or not state.isalpha():
            raise ValueError("UF deve conter exatamente 2 letras.")
        return state


class ClientRead(ClientBase):
    id: uuid.UUID
    rep_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    has_user: bool = False
    user_validated: bool = False

    model_config = {"from_attributes": True}
