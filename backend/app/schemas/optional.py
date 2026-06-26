import uuid
from typing import Optional
from pydantic import BaseModel, Field


class OptionalColorBase(BaseModel):
    category: str = Field(..., max_length=50)
    color_name: str = Field(..., max_length=100)


class OptionalColorCreate(OptionalColorBase):
    pass


class OptionalColorUpdate(BaseModel):
    category: Optional[str] = Field(None, max_length=50)
    color_name: Optional[str] = Field(None, max_length=100)


class OptionalColorRead(OptionalColorBase):
    id: uuid.UUID
    photo_url: Optional[str] = None

    model_config = {"from_attributes": True}
