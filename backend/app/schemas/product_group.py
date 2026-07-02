import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional


class ProductGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    ipi: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)


class ProductGroupCreate(ProductGroupBase):
    pass


class ProductGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    ipi: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class ProductGroupRead(ProductGroupBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
