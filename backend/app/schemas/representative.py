import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Literal, Optional
from datetime import datetime

from app.core.addresses import UF_SENTINEL, is_valid_uf
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
    state: str = Field(UF_SENTINEL, min_length=2, max_length=2)
    country: str = Field("BR", min_length=2, max_length=2)
    region: Optional[str] = Field(None, max_length=120)
    tax_id: Optional[str] = Field(None, max_length=40)
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
        """Ver `ClientBase.normalize_state`: a sentinela atravessa o `NOT NULL`
        dos mercados sem UF; o resto precisa ser sigla oficial."""
        if not isinstance(value, str):
            raise ValueError("UF deve ser informada como texto.")
        state = value.strip().upper()
        if state == UF_SENTINEL:
            return state
        if not is_valid_uf(state):
            raise ValueError("UF inválida. Use uma das 27 siglas oficiais (ex.: SP).")
        return state


class RepresentativeCreate(RepresentativeBase):
    # DEC-01/04 (catalog_permissions_r21): ausente não mexe na permissão.
    # Mandar só `catalog_ids` implica seleção específica.
    all_catalogs: Optional[bool] = None
    catalog_ids: Optional[list[uuid.UUID]] = Field(None, max_length=200)
    # price_list_access_r23: ausente não mexe na permissão. Mandar só
    # `price_list_codes` implica seleção específica.
    all_price_lists: Optional[bool] = None
    price_list_codes: Optional[list[Literal["lojista", "corporativo", "pvp", "arquiteto"]]] = Field(None, max_length=10)


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
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    region: Optional[str] = Field(None, max_length=120)
    tax_id: Optional[str] = Field(None, max_length=40)
    max_discount: Optional[Decimal] = Field(None, ge=0, le=100)
    # DEC-01/04 (catalog_permissions_r21): ausente não mexe na permissão.
    # Mandar só `catalog_ids` implica seleção específica.
    all_catalogs: Optional[bool] = None
    catalog_ids: Optional[list[uuid.UUID]] = Field(None, max_length=200)
    # price_list_access_r23: ausente não mexe na permissão. Mandar só
    # `price_list_codes` implica seleção específica.
    all_price_lists: Optional[bool] = None
    price_list_codes: Optional[list[Literal["lojista", "corporativo", "pvp", "arquiteto"]]] = Field(None, max_length=10)

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
        if state == UF_SENTINEL:
            return state
        if not is_valid_uf(state):
            raise ValueError("UF inválida. Use uma das 27 siglas oficiais (ex.: SP).")
        return state


class RepresentativeRead(RepresentativeBase):
    id: uuid.UUID
    market_code: str = "BR"
    created_at: datetime
    updated_at: datetime
    relationship_ended_at: datetime | None = None
    has_user: bool = False
    created_by_name: str | None = None
    all_catalogs: bool = True
    catalog_ids: list[uuid.UUID] = Field(default_factory=list)
    all_price_lists: bool = True
    price_list_codes: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
