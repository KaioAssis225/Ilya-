import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class OrderItemCreate(BaseModel):
    product_code: str
    qty: int = Field(..., ge=1)
    unit_price: Decimal = Field(..., ge=0, decimal_places=2)
    opt_aluminio: Optional[str] = None
    opt_madeira: Optional[str] = None
    opt_tecido: Optional[str] = None
    opt_couro: Optional[str] = None
    opt_corda: Optional[str] = None


class OrderCreate(BaseModel):
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    items: List[OrderItemCreate] = Field(..., min_length=1)


class OrderItemRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_code: str
    description: str
    is_circular: bool
    altura: Decimal
    largura: Decimal
    profundidade: Decimal
    opt_aluminio: Optional[str]
    opt_madeira: Optional[str]
    opt_tecido: Optional[str]
    opt_couro: Optional[str]
    opt_corda: Optional[str]
    qty: int
    unit_price: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderRead(BaseModel):
    id: uuid.UUID
    code: str
    orc_id: str
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID]
    total_value: Decimal
    notes: Optional[str]
    items: List[OrderItemRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
