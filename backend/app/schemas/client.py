import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, Literal
from datetime import datetime

from app.core.documents import normalize_cpf_cnpj


class ClientBase(BaseModel):
    name: str = Field(..., max_length=255)
    phone: str = Field(..., max_length=20)
    email: EmailStr | None = None
    # Opcional por decisão de produto: o cadastro rápido (feira, telefone) não
    # trava por falta de documento. Quando vem preenchido, o formato é cobrado.
    cpf_cnpj: Optional[str] = Field(None, max_length=14)
    cep: str = Field(..., max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: str = Field(..., max_length=255)
    city: str = Field(..., max_length=255)
    state: str = Field(..., min_length=2, max_length=2)
    price_profile: Literal["lojista", "corporativo"] = "lojista"
    max_discount: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)

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


class ClientCreate(ClientBase):
    # Sem isto, um cliente cadastrado por admin/cadastros nascia órfão e o
    # representante levava 403 ao tentar faturar para ele — sem conserto pela
    # API. Representante não escolhe: o vínculo é sempre com ele mesmo.
    rep_id: Optional[uuid.UUID] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    # Sem exclude_unset o PATCH não distingue "não mandou" de "mandou vazio";
    # o router usa exclude_unset, então ausente continua não mexendo no campo.
    cpf_cnpj: Optional[str] = Field(None, max_length=14)
    cep: Optional[str] = Field(None, max_length=20)
    numero: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, min_length=2, max_length=2)
    price_profile: Optional[Literal["lojista", "corporativo"]] = None
    max_discount: Optional[Decimal] = Field(None, ge=0, le=100)
    # Permite reatribuir a carteira e consertar cliente órfão (ver ClientCreate).
    rep_id: Optional[uuid.UUID] = None

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def normalize_document(cls, value: object) -> Optional[str]:
        # Campo opcional: enviar vazio limpa o documento. Só o formato é
        # cobrado, e apenas quando há algo para conferir.
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


class ClientRead(ClientBase):
    id: uuid.UUID
    rep_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    has_user: bool = False
    user_validated: bool = False
    created_by_name: str | None = None

    model_config = {"from_attributes": True}
