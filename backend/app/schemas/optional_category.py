import uuid
from pydantic import BaseModel, Field


class OptionalCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)


class OptionalCategoryCreate(OptionalCategoryBase):
    pass


class OptionalCategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)


class OptionalCategoryRead(OptionalCategoryBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
