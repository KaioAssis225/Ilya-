import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime

from app.core.documents import normalize_cpf_cnpj


class RepresentativeBase(BaseModel):
    name: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=20)
    email: EmailStr | None = None
    # Ver ClientBase: opcional por decisão de produto; o formato só é cobrado
    # quando o campo vem preenchido.
    cpf_cnpj: Optional[str] = Field(None, max_length=14)
    cep: str = Field(..., max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: str = Field(..., max_length=255)
    city: str = Field(..., max_length=255)
    state: str = Field(..., min_length=2, max_length=2)
    max_discount: Decimal = Field(default=Decimal("30.00"), ge=0, le=100)

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def normalize_document(cls, value: object) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_cpf_cnpj(value)

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("UF deve ser informada como texto.")
        state = value.strip().upper()
        if len(state) != 2 or not state.isascii() or not state.isalpha():
            raise ValueError("UF deve conter exatamente 2 letras.")
        return state


class RepresentativeCreate(RepresentativeBase):
    pass


class RepresentativeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    cpf_cnpj: Optional[str] = Field(None, max_length=14)
    cep: Optional[str] = Field(None, max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, min_length=2, max_length=2)
    max_discount: Optional[Decimal] = Field(None, ge=0, le=100)

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def normalize_document(cls, value: object) -> Optional[str]:
        # Ver ClientUpdate: enviar vazio limpa o documento.
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_cpf_cnpj(value)

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


class RepresentativeRead(RepresentativeBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    relationship_ended_at: datetime | None = None
    has_user: bool = False
    created_by_name: str | None = None

    model_config = {"from_attributes": True}
