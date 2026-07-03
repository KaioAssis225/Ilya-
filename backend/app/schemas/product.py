import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.schemas.optional import OptionalColorRead


class ProductSetItemCreate(BaseModel):
    product_code: str = Field(..., max_length=100)
    qty: int = Field(..., ge=1)


class ProductSetItemRead(BaseModel):
    product_code: str
    qty: int
    description: str
    photo_url: Optional[str] = None


class ProductSetComponentCreate(BaseModel):
    description: str
    is_circular: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    qty: int = Field(1, ge=1)
    optional_ids: List[uuid.UUID] = []


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
    product_code: str = Field(..., max_length=100)
    description: str
    type: str = Field(default="Outro", max_length=50)
    is_circular: bool = False
    is_set: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_lojista: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_corporativo: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    observacao: Optional[str] = None
    all_optionals_categories: Optional[str] = None


class ProductCreate(ProductBase):
    optional_ids: List[uuid.UUID] = []
    set_items: List[ProductSetItemCreate] = []
    components: List[ProductSetComponentCreate] = []


class ProductUpdate(BaseModel):
    product_code: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    type: Optional[str] = Field(None, max_length=50)
    is_circular: Optional[bool] = None
    is_set: Optional[bool] = None
    altura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    largura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    profundidade: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_lojista: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_corporativo: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    observacao: Optional[str] = None
    all_optionals_categories: Optional[str] = None
    optional_ids: Optional[List[uuid.UUID]] = None
    set_items: Optional[List[ProductSetItemCreate]] = None
    components: Optional[List[ProductSetComponentCreate]] = None


class ProductRead(ProductBase):
    id: uuid.UUID
    photo_url: Optional[str] = None
    optionals: List[OptionalColorRead] = []
    set_items: List[ProductSetItemRead] = []
    components: List[ProductSetComponentRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
