import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

from app.schemas.optional import OptionalColorRead


class ProductSetItemCreate(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(..., ge=1, le=100_000)


class ProductSetItemRead(BaseModel):
    product_code: str
    qty: int
    description: str
    photo_url: Optional[str] = None


class ProductSetComponentCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=20_000)
    is_circular: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    qty: int = Field(1, ge=1, le=100_000)
    optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=100)


class ProductSetComponentRead(BaseModel):
    id: uuid.UUID
    description: str
    is_circular: bool
    altura: Decimal
    largura: Decimal
    profundidade: Decimal
    qty: int
    optionals: List[OptionalColorRead] = []

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=20_000)
    type: str = Field(default="Outro", max_length=50)
    is_circular: bool = False
    is_set: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_lojista: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_corporativo: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    observacao: Optional[str] = Field(None, max_length=20_000)
    all_optionals_categories: Optional[str] = Field(None, max_length=2_000)


class ProductCreate(ProductBase):
    optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=500)
    set_items: List[ProductSetItemCreate] = Field(default_factory=list, max_length=500)
    components: List[ProductSetComponentCreate] = Field(default_factory=list, max_length=500)


class ProductUpdate(BaseModel):
    product_code: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=20_000)
    type: Optional[str] = Field(None, max_length=50)
    is_circular: Optional[bool] = None
    is_set: Optional[bool] = None
    altura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    largura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    profundidade: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_lojista: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_corporativo: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    observacao: Optional[str] = Field(None, max_length=20_000)
    all_optionals_categories: Optional[str] = Field(None, max_length=2_000)
    optional_ids: Optional[List[uuid.UUID]] = Field(None, max_length=500)
    set_items: Optional[List[ProductSetItemCreate]] = Field(None, max_length=500)
    components: Optional[List[ProductSetComponentCreate]] = Field(None, max_length=500)


class ProductBatchRequest(BaseModel):
    product_codes: List[str] = Field(..., min_length=1, max_length=100)

    @field_validator("product_codes")
    @classmethod
    def validate_codes(cls, values: List[str]) -> List[str]:
        if any(not value or len(value) > 100 for value in values):
            raise ValueError("Cada código deve ter entre 1 e 100 caracteres.")
        return values


class ProductRead(ProductBase):
    id: uuid.UUID
    photo_url: Optional[str] = None
    optionals: List[OptionalColorRead] = []
    set_items: List[ProductSetItemRead] = []
    components: List[ProductSetComponentRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
