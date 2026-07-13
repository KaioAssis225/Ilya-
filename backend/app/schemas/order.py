import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class OrderItemCreate(BaseModel):
    product_code: str
    qty: int = Field(..., ge=1)
    discount: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=2)
    opt_categories: Dict[str, str] = Field(default_factory=dict)


class OrderCreate(BaseModel):
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    items: List[OrderItemCreate] = Field(..., min_length=1)


class OrderUpdate(BaseModel):
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    items: Optional[List[OrderItemCreate]] = Field(None, min_length=1)


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


class OrderListRead(BaseModel):
    """Versão leve para listagem — NÃO inclui os blobs de assinatura (V-M7),
    apenas as flags booleanas de status. ~750 KB por assinatura economizados."""
    id: uuid.UUID
    code: str
    orc_id: str
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID]
    total_value: Decimal
    total_ipi: Decimal = Decimal("0")
    total_with_ipi: Decimal = Decimal("0")
    is_finalized: bool = False
    external_code: Optional[str] = None
    notes: Optional[str]
    rep_signed: bool = False
    client_signed: bool = False
    items: List[OrderItemRead]
    history: List[OrderHistoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
