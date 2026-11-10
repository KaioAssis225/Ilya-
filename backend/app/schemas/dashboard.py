import uuid
from datetime import date
from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    revenue_total: float
    revenue_finalized: float
    revenue_open: float
    revenue_cancelled: float
    orders_total: int
    orders_finalized: int
    orders_open: int
    orders_cancelled: int
    # Etapas dos pedidos confirmados (aba "Pedidos"); zeradas na aba de orçamentos.
    revenue_production: float = 0
    revenue_delivered: float = 0
    orders_production: int = 0
    orders_delivered: int = 0


class ChartPoint(BaseModel):
    key: str  # YYYY-MM-DD (dia/segunda da semana) ou YYYY-MM (mês)
    revenue: float
    orders: int


class RepresentativeRanking(BaseModel):
    name: str
    orders: int
    revenue: float


class ProductRanking(BaseModel):
    product_code: str
    description: str
    quantity: float
    revenue: float


class DashboardOverview(BaseModel):
    kind: str | None = None  # "quotes" | "orders" | None (sem separação)
    start_date: date
    end_date: date
    granularity: str  # "day" | "week" | "month"
    metrics: DashboardMetrics
    chart: list[ChartPoint]
    representatives: list[RepresentativeRanking]
    products: list[ProductRanking]


class ClientContactRow(BaseModel):
    id: uuid.UUID
    name: str
    contact_name: str | None = None
    phone: str
    email: str | None = None
    city: str
    country: str
    rep_id: uuid.UUID | None = None
    rep_name: str | None = None
    contacted: bool


class ClientsDashboard(BaseModel):
    # Indicadores da carteira inteira do usuário (mercado + ownership), sem
    # depender do filtro/busca da lista.
    total: int
    contacted: int
    not_contacted: int
    contacted_pct: float
    # Lista filtrada e paginada.
    filtered_total: int
    items: list[ClientContactRow]
