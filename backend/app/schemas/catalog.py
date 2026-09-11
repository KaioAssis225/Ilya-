import uuid
from pydantic import BaseModel, Field


class CatalogBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class CatalogCreate(CatalogBase):
    pass


class CatalogUpdate(CatalogBase):
    pass


class CatalogRead(CatalogBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
