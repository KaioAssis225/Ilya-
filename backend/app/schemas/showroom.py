import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PriceListCode = Literal["lojista", "arquiteto", "corporativo", "pvp"]


class ShowroomBoxCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price_list_code: PriceListCode = "lojista"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Informe o nome da box.")
        return value


class ShowroomBoxUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price_list_code: PriceListCode | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Informe o nome da box.")
        return value

    @model_validator(mode="after")
    def has_change(self):
        if self.name is None and self.price_list_code is None:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self


class ShowroomOptionalChoiceInput(BaseModel):
    """Um opcional do cadastro ou, em uma aplicação, a opção "Customizado"
    (``custom``), como no orçamento EU."""

    optional_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    category_code: str | None = Field(default=None, min_length=1, max_length=50)
    custom: bool = False

    @model_validator(mode="after")
    def identifies_one_slot(self):
        if (self.application_id is None) == (self.category_code is None):
            raise ValueError("Informe a aplicação ou a categoria do opcional.")
        if self.custom:
            if self.optional_id is not None or self.application_id is None:
                raise ValueError("Customizado vale só em uma aplicação, sem opcional do cadastro.")
        elif self.optional_id is None:
            raise ValueError("Escolha um opcional ou a opção Customizado.")
        if self.category_code is not None:
            self.category_code = self.category_code.strip()
        return self


class ShowroomItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=1_000_000)
    optional_choices: list[ShowroomOptionalChoiceInput] = Field(
        default_factory=list, max_length=100,
    )


class ShowroomItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000)


class ShowroomProductRead(BaseModel):
    id: uuid.UUID
    product_code: str
    description: str
    thumbnail_url: str | None = None
    unit_price: Decimal


class ShowroomOptionalChoiceRead(BaseModel):
    application_id: uuid.UUID | None = None
    application_name: str | None = None
    application_name_en: str | None = None
    category_code: str
    category_name: str
    optional_id: uuid.UUID | None = None
    optional_name: str
    custom: bool = False
    component_name: str | None = None
    thumbnail_url: str | None = None


class ShowroomItemRead(ShowroomProductRead):
    item_id: uuid.UUID
    quantity: int
    line_total: Decimal
    optional_choices: list[ShowroomOptionalChoiceRead] = Field(default_factory=list)


class ShowroomBoxRead(BaseModel):
    id: uuid.UUID
    name: str
    market_code: Literal["EU"] = "EU"
    price_list_code: PriceListCode
    currency: Literal["EUR"] = "EUR"
    items: list[ShowroomItemRead] = Field(default_factory=list)
    item_count: int = 0
    total_quantity: int = 0
    total_value: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime


class ShowroomTransferBox(BaseModel):
    type: Literal["box"]
    box_id: uuid.UUID


class ShowroomTransferCreate(BaseModel):
    """Transferência direta: só para outra box. Orçamento não é destino: a peça
    vai para a tela Novo orçamento e a baixa acontece ao salvar
    (``showroom_source_item_id`` no item do pedido); orçamento existente nunca
    recebe peça do estoque."""

    item_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000)
    destination: ShowroomTransferBox


class ShowroomTransferRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    created_by_name: str
    source_box_id: uuid.UUID | None = None
    source_box_name: str
    destination_type: Literal["box", "order"]
    destination_box_id: uuid.UUID | None = None
    destination_box_name: str | None = None
    destination_order_id: uuid.UUID | None = None
    destination_order_code: str | None = None
    product_code: str
    quantity: int
    optional_choices: list[ShowroomOptionalChoiceRead] = Field(default_factory=list)


class ShowroomTransferResult(BaseModel):
    transfer: ShowroomTransferRead
    box: ShowroomBoxRead
