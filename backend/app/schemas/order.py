import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.core.vat_exemption import VatExemptionCode, vat_exemption_label

OrderStage = Literal["production", "delivered"]


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
    qty: Optional[Decimal] = Field(None, gt=0, le=1_000_000, decimal_places=2)
    area_width_m: Optional[Decimal] = Field(None, gt=0, le=1000, decimal_places=3)
    area_depth_m: Optional[Decimal] = Field(None, gt=0, le=1000, decimal_places=3)
    area_pieces: Optional[int] = Field(None, ge=1, le=1000)
    discount: Decimal = Field(Decimal("0"), ge=0, le=100, decimal_places=2)
    opt_categories: Dict[str, str] = Field(default_factory=dict, max_length=50)
    optional_choices: List[OptionalChoiceCreate] = Field(default_factory=list, max_length=100)
    source_order_item_id: Optional[uuid.UUID] = None
    preserve_optional_choices: bool = False
    comment: Optional[str] = Field(None, max_length=1000)
    is_special: bool = False
    special_code: Optional[str] = Field(None, max_length=100)
    special_percent: Optional[Decimal] = Field(None, gt=Decimal("-100"), le=Decimal("1000"), decimal_places=2)

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

    @model_validator(mode="after")
    def validate_area_dimensions(self) -> "OrderItemCreate":
        has_width = self.area_width_m is not None
        has_depth = self.area_depth_m is not None
        if has_width != has_depth:
            raise ValueError("Informe largura e profundidade do tapete.")
        if not has_width and not has_depth and self.qty is None:
            raise ValueError("Informe a quantidade do item.")
        return self

    @model_validator(mode="after")
    def validate_special_consistency(self) -> "OrderItemCreate":
        if self.is_special:
            if self.special_percent is None:
                raise ValueError("Informe a percentagem do especial / Provide the special percentage.")
            if self.discount != 0:
                raise ValueError("O desconto deve ser 0 para itens especiais / Discount must be 0 for special items.")
        elif self.special_code is not None or self.special_percent is not None:
            raise ValueError("Campos de especial só podem ser usados em itens especiais / Special fields require is_special.")
        return self


class OrderCreate(BaseModel):
    client_id: uuid.UUID
    rep_id: Optional[uuid.UUID] = None
    # Só EU. Ausente herda da revisão de origem (ou fica com IVA); com isenção
    # o motivo é obrigatório.
    vat_exempt: Optional[bool] = None
    vat_exemption_code: Optional[VatExemptionCode] = None
    # Só aceita a tabela de faturamento do cliente (ou a da revisão de
    # origem); outra tabela é 422. Ausente usa o perfil do cliente.
    price_list_code: Optional[Literal["lojista", "corporativo", "pvp", "arquiteto"]] = None
    notes: Optional[str] = Field(None, max_length=10_000)
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=500)
    locale: Optional[Literal["pt-PT", "en-GB"]] = None
    supersedes_order_id: Optional[uuid.UUID] = None
    # Orçamento novo preenchido a partir de outro (Copiar). Os itens que ainda
    # apontam para um item do pedido de origem (`source_order_item_id`) seguem as
    # regras de cópia: o que não pode ser copiado é pulado e avisado em vez de
    # derrubar o orçamento. Os demais itens seguem a criação normal.
    copy_source_order_id: Optional[uuid.UUID] = None


class OrderUpdate(BaseModel):
    rep_id: Optional[uuid.UUID] = None
    # Ausente mantém o estado atual; mudar exige reenviar os itens.
    vat_exempt: Optional[bool] = None
    vat_exemption_code: Optional[VatExemptionCode] = None
    price_list_code: Optional[Literal["lojista", "corporativo", "pvp", "arquiteto"]] = None
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
    area_width_m: Optional[Decimal] = None
    area_depth_m: Optional[Decimal] = None
    area_pieces: int = 1
    unit_price: Decimal
    discount: Decimal = Decimal("0")
    ipi_rate: Decimal = Decimal("0")
    ipi_value: Decimal = Decimal("0")
    tax_label: str = "IPI"
    currency: str = "BRL"
    observacao: Optional[str] = None
    comment: Optional[str] = None
    is_special: bool = False
    special_code: Optional[str] = None
    special_percent: Optional[Decimal] = None
    # Opcionais ainda sem escolha (só preenchido em orçamento EU em aberto).
    pending_optionals: List[str] = Field(default_factory=list)
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


class OrderCopySkipped(BaseModel):
    product_code: str
    reason: str


class OrderRead(BaseModel):
    # Só preenchido na resposta da criação a partir de uma cópia.
    copy_skipped: List[OrderCopySkipped] = Field(default_factory=list)
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
    order_stage: Optional[OrderStage] = None
    production_started_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    document_version: int = 1
    supersedes_order_id: Optional[uuid.UUID] = None
    revision_number: int = 1
    external_code: Optional[str] = None
    vat_exempt: bool = False
    vat_exemption_code: Optional[str] = None
    notes: Optional[str]
    items: List[OrderItemRead]
    history: List[OrderHistoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def vat_exemption_label(self) -> Optional[str]:
        return vat_exemption_label(self.vat_exemption_code, self.locale)

    model_config = {"from_attributes": True}


class OrderStageUpdate(BaseModel):
    stage: OrderStage


class OrderListItemRead(BaseModel):
    product_code: str
    is_special: bool = False
    special_code: Optional[str] = None
    special_percent: Optional[Decimal] = None
    qty: float
    area_width_m: Optional[Decimal] = None
    area_depth_m: Optional[Decimal] = None
    area_pieces: int = 1


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
    order_stage: Optional[OrderStage] = None
    production_started_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    items: List[OrderListItemRead] = Field(default_factory=list)
    created_at: datetime


class OrderCopyRequest(BaseModel):
    """Itens do pedido de origem a copiar para um novo orçamento."""
    item_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)


class OrderCopyRead(BaseModel):
    order: OrderRead
    skipped: List[OrderCopySkipped] = Field(default_factory=list)
