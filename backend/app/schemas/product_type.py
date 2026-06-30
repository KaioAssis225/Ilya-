import uuid
from pydantic import BaseModel, Field


class ProductTypeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class ProductTypeCreate(ProductTypeBase):
    pass


class ProductTypeUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class ProductTypeRead(ProductTypeBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
