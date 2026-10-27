import uuid
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime

from app.schemas.optional import OptionalColorRead
from app.schemas.catalog import CatalogRead


class OptionalApplicationWrite(BaseModel):
    id: Optional[uuid.UUID] = None
    category_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=120)
    name_en: Optional[str] = Field(None, max_length=120)
    required: bool = False
    display_order: int = Field(0, ge=0)
    allow_all: bool = False
    allow_repeat: bool = True
    allowed_optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=500)


class OptionalApplicationRead(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_code: str
    category_name: str
    name: str
    name_en: Optional[str] = None
    required: bool
    display_order: int
    allow_all: bool
    allow_repeat: bool
    allowed_optionals: List[OptionalColorRead] = Field(default_factory=list)


def _strip_product_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip()


class ProductSetItemCreate(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(..., ge=1, le=100_000)


class ProductSetItemRead(BaseModel):
    product_code: str
    qty: int
    description: str
    photo_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ProductSetComponentCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    description: str = Field(..., min_length=1, max_length=20_000)
    is_circular: bool = False
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    qty: int = Field(1, ge=1, le=100_000)
    optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=100)
    optional_applications: Optional[List[OptionalApplicationWrite]] = Field(None, max_length=100)


class ProductSetComponentRead(BaseModel):
    id: uuid.UUID
    description: str
    is_circular: bool
    altura: Decimal
    largura: Decimal
    profundidade: Decimal
    qty: int
    optionals: List[OptionalColorRead] = []
    optional_applications: List[OptionalApplicationRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=20_000)
    ean: Optional[str] = Field(None, pattern=r"^\d{8,13}$")
    summary: Optional[str] = Field(None, max_length=1_000)
    article_category_path: Optional[str] = Field(None, max_length=255)
    type: str = Field(default="Outro", min_length=1, max_length=50)
    catalog_id: Optional[uuid.UUID] = None
    is_circular: bool = False
    is_set: bool = False
    area_limit_enabled: bool = False
    max_area_m2: Optional[Decimal] = Field(
        None, gt=0, le=100_000, decimal_places=2
    )
    altura: Decimal = Field(..., ge=0, decimal_places=2)
    largura: Decimal = Field(..., ge=0, decimal_places=2)
    profundidade: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_lojista: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_corporativo: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    observacao: Optional[str] = Field(None, max_length=20_000)
    all_optionals_categories: Optional[str] = Field(None, max_length=2_000)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return _strip_product_type(value) or ""

    @field_validator("ean", "summary", mode="before")
    @classmethod
    def normalize_article_text(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("article_category_path", mode="before")
    @classmethod
    def normalize_article_category(cls, value: Optional[str]) -> Optional[str]:
        if not isinstance(value, str) or not value.strip():
            return None
        parts = [part.strip() for part in value.split("/")]
        if any(not part or len(part) > 80 for part in parts):
            raise ValueError("Cada nível da categoria deve ter entre 1 e 80 caracteres.")
        return " / ".join(parts)

    @model_validator(mode="after")
    def validate_area_limit(self):
        if self.area_limit_enabled and self.max_area_m2 is None:
            raise ValueError(
                "Informe o limite máximo em m² quando o limite de área estiver ativado."
            )
        return self


class ProductCreate(ProductBase):
    # DEC-02 (catalog_permissions_r21): o catálogo define aba e permissão.
    catalog_id: uuid.UUID
    price_pvp: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    price_arquiteto: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    description_pt_pt: Optional[str] = Field(None, min_length=1, max_length=20_000)
    description_en: Optional[str] = Field(None, min_length=1, max_length=20_000)
    optional_ids: List[uuid.UUID] = Field(default_factory=list, max_length=500)
    optional_applications: List[OptionalApplicationWrite] = Field(default_factory=list, max_length=100)
    set_items: List[ProductSetItemCreate] = Field(default_factory=list, max_length=500)
    components: List[ProductSetComponentCreate] = Field(default_factory=list, max_length=500)


class ProductUpdate(BaseModel):
    product_code: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=20_000)
    ean: Optional[str] = Field(None, pattern=r"^\d{8,13}$")
    summary: Optional[str] = Field(None, max_length=1_000)
    article_category_path: Optional[str] = Field(None, max_length=255)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    catalog_id: Optional[uuid.UUID] = None
    is_circular: Optional[bool] = None
    is_set: Optional[bool] = None
    area_limit_enabled: Optional[bool] = None
    max_area_m2: Optional[Decimal] = Field(
        None, gt=0, le=100_000, decimal_places=2
    )
    altura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    largura: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    profundidade: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_lojista: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_corporativo: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_pvp: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    price_arquiteto: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    description_pt_pt: Optional[str] = Field(None, min_length=1, max_length=20_000)
    description_en: Optional[str] = Field(None, min_length=1, max_length=20_000)
    observacao: Optional[str] = Field(None, max_length=20_000)
    all_optionals_categories: Optional[str] = Field(None, max_length=2_000)
    optional_ids: Optional[List[uuid.UUID]] = Field(None, max_length=500)
    optional_applications: Optional[List[OptionalApplicationWrite]] = Field(None, max_length=100)
    set_items: Optional[List[ProductSetItemCreate]] = Field(None, max_length=500)
    components: Optional[List[ProductSetComponentCreate]] = Field(None, max_length=500)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Optional[str]) -> Optional[str]:
        return _strip_product_type(value)

    @field_validator("ean", "summary", mode="before")
    @classmethod
    def normalize_article_text(cls, value: Optional[str]) -> Optional[str]:
        return ProductBase.normalize_article_text(value)

    @field_validator("article_category_path", mode="before")
    @classmethod
    def normalize_article_category(cls, value: Optional[str]) -> Optional[str]:
        return ProductBase.normalize_article_category(value)

    @field_validator("catalog_id")
    @classmethod
    def keep_catalog(cls, value: Optional[uuid.UUID]) -> uuid.UUID:
        # Só roda quando o campo vem no PATCH: ausente não mexe, nulo não
        # remove o catálogo (DEC-02).
        if value is None:
            raise ValueError("Catálogo é obrigatório.")
        return value


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
    # Bloco 96: preço que a role logada não pode ver sai como null em vez de
    # trafegar até o browser. Conta de cliente-final recebe apenas o preço do
    # próprio perfil de faturamento (lojista OU corporativo).
    price: Optional[Decimal] = None
    price_lojista: Optional[Decimal] = None
    price_corporativo: Optional[Decimal] = None
    market_code: str = "BR"
    currency: str = "BRL"
    market_prices: dict[str, Decimal] = Field(default_factory=dict)
    description_pt_pt: Optional[str] = None
    description_en: Optional[str] = None
    # IVA aprovado do produto em Portugal; null no Brasil ou enquanto pendente.
    vat_rate: Optional[Decimal] = None
    photo_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    catalog: Optional[CatalogRead] = None
    optionals: List[OptionalColorRead] = []
    optional_applications: List[OptionalApplicationRead] = Field(default_factory=list)
    set_items: List[ProductSetItemRead] = []
    components: List[ProductSetComponentRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
