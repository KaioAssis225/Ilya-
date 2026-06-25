import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProductBase(BaseModel):
    product_code: str = Field(..., max_length=100)
    description: str
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(..., ge=0, decimal_places=2)
    opt_aluminio: Optional[str] = Field(None, max_length=50)
    opt_tecido: Optional[str] = Field(None, max_length=50)
    opt_corda: Optional[str] = Field(None, max_length=50)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_code: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    altura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    largura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    profundidade: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    opt_aluminio: Optional[str] = Field(None, max_length=50)
    opt_tecido: Optional[str] = Field(None, max_length=50)
    opt_corda: Optional[str] = Field(None, max_length=50)


class ProductRead(ProductBase):
    id: uuid.UUID
    photo_path: Optional[str] = None
    photo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
