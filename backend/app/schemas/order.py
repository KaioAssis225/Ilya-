import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OrderItemCreate(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(..., ge=1, le=1_000_000)
    discount: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=2)
    opt_categories: Dict[str, str] = Field(default_factory=dict, max_length=50)

    @field_validator("opt_categories")
    @classmethod
    def validate_optional_values(cls, values: Dict[str, str]) -> Dict[str, str]:
        if any(
            not category
            or len(category) > 50
            or not color
            or len(color) > 100
            for category, color in values.items()
        ):
            raise ValueError("Categoria ou cor opcional fora do tamanho permitido.")
        return values


class OrderCreate(BaseModel):
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = Field(None, max_length=10_000)
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=500)


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
    qty: int
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    ipi_rate: Decimal = Decimal("0")
    ipi_value: Decimal = Decimal("0")
    observacao: Optional[str] = None
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
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderRead(BaseModel):
    id: uuid.UUID
    code: str
    orc_id: str
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID]
    total_value: Decimal
    total_ipi: Decimal = Decimal("0")
    total_with_ipi: Decimal = Decimal("0")
    is_finalized: bool = False
    is_cancelled: bool = False
    external_code: Optional[str] = None
    notes: Optional[str]
    rep_signed: bool = False
    client_signed: bool = False
    rep_signature: Optional[str] = None
    client_signature: Optional[str] = None
    items: List[OrderItemRead]
    history: List[OrderHistoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListItemRead(BaseModel):
    product_code: str
    qty: int


class OrderListRead(BaseModel):
    """Projeção mínima para listagens e paginação.

    Não inclui assinaturas, histórico, observações nem os campos completos dos
    itens. O detalhe continua disponível em ``GET /orders/{id}``.
    """

    id: uuid.UUID
    code: str
    orc_id: str
    client_id: uuid.UUID
    client_name: str
    rep_id: Optional[uuid.UUID]
    rep_name: Optional[str] = None
    total_value: Decimal
    total_with_ipi: Decimal = Decimal("0")
    is_finalized: bool = False
    is_cancelled: bool = False
    items: List[OrderListItemRead] = Field(default_factory=list)
    created_at: datetime
