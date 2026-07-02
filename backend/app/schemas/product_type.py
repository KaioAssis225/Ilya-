import uuid
from pydantic import BaseModel, Field
from typing import Optional

from app.schemas.product_group import ProductGroupRead


class ProductTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    group_id: Optional[uuid.UUID] = None


class ProductTypeCreate(ProductTypeBase):
    pass


class ProductTypeUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    group_id: Optional[uuid.UUID] = None


class ProductTypeRead(ProductTypeBase):
    id: uuid.UUID
    group: Optional[ProductGroupRead] = None

    model_config = {"from_attributes": True}
