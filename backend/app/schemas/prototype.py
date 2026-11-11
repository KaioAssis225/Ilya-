"""Corpos de entrada da área de protótipos (EU).

Mesmos campos do produto normal, menos o que não faz sentido num protótipo:
o código (`PROT-xxxx`, gerado no servidor), EAN e categoria de artigo (só
servem ao Moloni, para onde protótipo nunca vai), conjunto/componentes e limite
de área. O IVA é informado pelo criador (`vat_rate`).
"""
import uuid
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.product_dimensions import ensure_dimension_within_limit
from app.schemas.product import OptionalApplicationWrite

DEFAULT_PROTOTYPE_VAT_RATE = Decimal("23.00")


def _strip(value: Optional[str]) -> Optional[str]:
    return value.strip() if isinstance(value, str) else value


class PrototypeCreate(BaseModel):
    description_pt_pt: str = Field(..., min_length=1, max_length=20_000)
    description_en: str = Field(..., min_length=1, max_length=20_000)
    summary: Optional[str] = Field(None, max_length=1_000)
    type: str = Field(default="Outro", min_length=1, max_length=50)
    catalog_id: uuid.UUID
    is_circular: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_lojista: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_corporativo: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_pvp: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_arquiteto: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    vat_rate: Decimal = Field(DEFAULT_PROTOTYPE_VAT_RATE, ge=0, le=100, decimal_places=2)
    observacao: Optional[str] = Field(None, max_length=20_000)
    optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=500)
    optional_applications: List[OptionalApplicationWrite] = Field(default_factory=list, max_length=100)

    model_config = {"extra": "forbid"}

    @field_validator("type", "description_pt_pt", "description_en", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _strip(value)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value):
        value = _strip(value)
        return value or None

    @field_validator("altura", "largura", "profundidade")
    @classmethod
    def validate_dimension_limit(cls, value: Decimal) -> Decimal:
        return ensure_dimension_within_limit(value)


class PrototypeUpdate(BaseModel):
    """Atualização parcial: só o que vier no corpo muda."""

    description_pt_pt: Optional[str] = Field(None, min_length=1, max_length=20_000)
    description_en: Optional[str] = Field(None, min_length=1, max_length=20_000)
    summary: Optional[str] = Field(None, max_length=1_000)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    catalog_id: Optional[uuid.UUID] = None
    is_circular: Optional[bool] = None
    altura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    largura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    profundidade: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_lojista: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_corporativo: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_pvp: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_arquiteto: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    vat_rate: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    observacao: Optional[str] = Field(None, max_length=20_000)
    optional_ids: Optional[List[uuid.UUID]] = Field(None, max_length=500)
    optional_applications: Optional[List[OptionalApplicationWrite]] = Field(None, max_length=100)

    model_config = {"extra": "forbid"}

    @field_validator("type", "description_pt_pt", "description_en", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _strip(value)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value):
        value = _strip(value)
        return value or None

    @field_validator("catalog_id", "vat_rate")
    @classmethod
    def keep_required(cls, value):
        # Só roda quando o campo vem no PATCH: nulo não remove catálogo nem IVA.
        if value is None:
            raise ValueError("Valor obrigatório.")
        return value

    @field_validator("altura", "largura", "profundidade")
    @classmethod
    def validate_dimension_limit(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        return ensure_dimension_within_limit(value)


class PrototypeOptionWrite(BaseModel):
    """Opção de um grupo do protótipo. Com `id`, mantém/renomeia a existente."""

    id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=1, max_length=100)

    model_config = {"extra": "forbid"}

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return _strip(value)


class PrototypeOptionalGroupWrite(BaseModel):
    """Grupo de opcionais que existe só neste protótipo."""

    name: str = Field(..., min_length=1, max_length=100)
    options: List[PrototypeOptionWrite] = Field(..., min_length=1, max_length=100)

    model_config = {"extra": "forbid"}

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return _strip(value)


class PrototypeOptionRead(BaseModel):
    id: uuid.UUID
    name: str


class PrototypeOptionalGroupRead(BaseModel):
    """`id` é o `category_id` a usar em `optional_applications` do protótipo."""

    id: uuid.UUID
    code: str
    name: str
    options: List[PrototypeOptionRead]
