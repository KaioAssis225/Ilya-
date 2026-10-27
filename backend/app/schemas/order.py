import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Valor da escolha customizada no seletor antigo (opt_categories). Pedidos
# anteriores podem trazer "Customizado: <texto>", da época da caixa de texto.
CUSTOM_LEGACY_VALUE = "Customizado"


def is_legacy_custom(value: str) -> bool:
    return value == CUSTOM_LEGACY_VALUE or value.startswith(CUSTOM_LEGACY_VALUE + ":")


class OptionalChoiceCreate(BaseModel):
    """Um opcional do cadastro (`optional_id`) ou a opção "Customizado"
    (`custom_text` presente; vazio quando não há descrição) — nunca os dois."""
    application_id: uuid.UUID
    optional_id: Optional[uuid.UUID] = None
    custom_text: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def validate_single_choice(self) -> "OptionalChoiceCreate":
        if self.custom_text is not None:
            self.custom_text = self.custom_text.strip()
        if (self.optional_id is None) == (self.custom_text is None):
            raise ValueError("Escolha um opcional ou a opção Customizado.")
        return self


class OptionalChoiceRead(BaseModel):
    id: uuid.UUID
    application_id: Optional[uuid.UUID] = None
    optional_id: Optional[uuid.UUID] = None
    application_name: str
    application_name_en: Optional[str] = None
    category_code: str
    category_name: str
    optional_name: str
    custom_text: Optional[str] = None
    component_name: Optional[str] = None
    display_order: int

    model_config = {"from_attributes": True}


class OrderItemCreate(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    qty: Decimal = Field(..., gt=0, le=1_000_000, decimal_places=2)
    discount: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=2)
    opt_categories: Dict[str, str] = Field(default_factory=dict, max_length=50)
    optional_choices: List[OptionalChoiceCreate] = Field(default_factory=list, max_length=100)
    source_order_item_id: Optional[uuid.UUID] = None
    preserve_optional_choices: bool = False
    comment: Optional[str] = Field(None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: Optional[str]) -> Optional[str]:
        return (value or "").strip() or None

    @field_validator("opt_categories")
    @classmethod
    def validate_optional_values(cls, values: Dict[str, str]) -> Dict[str, str]:
        # O texto de um "Customizado: <texto>" antigo pode passar de 100 caracteres.
        def invalid_color(color: str) -> bool:
            if is_legacy_custom(color):
                return len(color) > len(CUSTOM_LEGACY_VALUE) + 1001
            return not color or len(color) > 100

        if any(
            not category
            or len(category) > 50
            or invalid_color(color)
            for category, color in values.items()
        ):
            raise ValueError("Categoria ou cor opcional fora do tamanho permitido.")
        return values


class OrderCreate(BaseModel):
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = Field(None, max_length=10_000)
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=500)
    locale: Optional[Literal["pt-PT", "en-GB"]] = None
    supersedes_order_id: Optional[uuid.UUID] = None


class OrderUpdate(BaseModel):
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = Field(None, max_length=10_000)
    items: Optional[List[OrderItemCreate]] = Field(
        None,
        min_length=1,
        max_length=500,
    )


class OrderItemRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_code: str
    description: str
    is_circular: bool
    altura: Decimal
    largura: Decimal
    profundidade: Decimal
    opt_categories: Dict[str, str] = Field(default_factory=dict)
    optional_choices: List[OptionalChoiceRead] = Field(default_factory=list)
    qty: float
    sold_by_area: bool = False
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    ipi_rate: Decimal = Decimal("0")
    ipi_value: Decimal = Decimal("0")
    tax_label: str = "IPI"
    currency: str = "BRL"
    observacao: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HistoryUserRead(BaseModel):
    id: uuid.UUID
    full_name: str

    model_config = {"from_attributes": True}


class OrderHistoryRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user: Optional[HistoryUserRead] = None
    action: str
    details: Optional[str] = None
    items_snapshot: Optional[list] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderRead(BaseModel):
    id: uuid.UUID
    code: str
    orc_id: str
    market_code: str = "BR"
    price_list_code: str = "lojista"
    currency: str = "BRL"
    locale: str = "pt-BR"
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID]
    catalog_id: Optional[uuid.UUID] = None
    catalog_name: Optional[str] = None
    total_value: Decimal
    total_ipi: Decimal = Decimal("0")
    total_with_ipi: Decimal = Decimal("0")
    is_finalized: bool = False
    is_cancelled: bool = False
    finalized_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    document_version: int = 1
    supersedes_order_id: Optional[uuid.UUID] = None
    revision_number: int = 1
    external_code: Optional[str] = None
    notes: Optional[str]
    items: List[OrderItemRead]
    history: List[OrderHistoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListItemRead(BaseModel):
    product_code: str
    qty: float


class OrderListRead(BaseModel):
    """Projeção mínima para listagens e paginação.

    Não inclui assinaturas, histórico, observações nem os campos completos dos
    itens. O detalhe continua disponível em ``GET /orders/{id}``.
    """

    id: uuid.UUID
    code: str
    orc_id: str
    market_code: str = "BR"
    currency: str = "BRL"
    client_id: uuid.UUID
    client_name: str
    rep_id: Optional[uuid.UUID]
    rep_name: Optional[str] = None
    catalog_id: Optional[uuid.UUID] = None
    catalog_name: Optional[str] = None
    total_value: Decimal
    total_with_ipi: Decimal = Decimal("0")
    is_finalized: bool = False
    is_cancelled: bool = False
    finalized_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    items: List[OrderListItemRead] = Field(default_factory=list)
    created_at: datetime
