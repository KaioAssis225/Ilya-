from datetime import date
from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    revenue_total: float
    revenue_finalized: float
    revenue_open: float
    orders_total: int
    orders_finalized: int
    orders_open: int


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
    quantity: int
    revenue: float


class DashboardOverview(BaseModel):
    start_date: date
    end_date: date
    granularity: str  # "day" | "week" | "month"
    metrics: DashboardMetrics
    chart: list[ChartPoint]
    representatives: list[RepresentativeRanking]
    products: list[ProductRanking]
