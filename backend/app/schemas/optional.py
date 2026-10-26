import uuid
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class OptionalColorBase(BaseModel):
    category: str = Field(..., max_length=50)
    color_name: str = Field(..., max_length=100)
    brand: Literal["ILYA", "IBTW"] = "ILYA"


class OptionalColorCreate(OptionalColorBase):
    pass


class OptionalColorUpdate(BaseModel):
    category: Optional[str] = Field(None, max_length=50)
    color_name: Optional[str] = Field(None, max_length=100)
    brand: Optional[Literal["ILYA", "IBTW"]] = None

    @field_validator("brand")
    @classmethod
    def brand_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Informe ILYA ou IBTW.")
        return value


class OptionalPhotoVariant(BaseModel):
    url: str
    # Limite do maior lado; fontes menores são servidas no tamanho que têm.
    max_side: int


class OptionalPhotoVariants(BaseModel):
    thumb: OptionalPhotoVariant
    gallery: OptionalPhotoVariant
    zoom: OptionalPhotoVariant


class OptionalColorRead(OptionalColorBase):
    id: uuid.UUID
    market_code: str
    photo_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    photo_variants: Optional[OptionalPhotoVariants] = None
    # Só na resposta do upload: a foto enviada é menor que o recomendado.
    photo_low_resolution: Optional[bool] = None

    model_config = {"from_attributes": True}
