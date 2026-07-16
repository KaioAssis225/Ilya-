import uuid
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, require_dashboard_access
from app.core.regions import region_for_state
from app.models.client import Client
from app.models.order import Order
from app.models.representative import Representative
from app.models.user import User
from app.schemas.dashboard import (
    DashboardOverview,
    DashboardMetrics,
    ChartPoint,
    RepresentativeRanking,
    ProductRanking,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _week_key(d: date) -> str:
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


@router.get("/overview", response_model=DashboardOverview)
async def get_overview(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    rep_id: uuid.UUID | None = Query(default=None),
    region: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_dashboard_access),
):
    # Bloco 95: sem período informado, olha os últimos 30 dias corridos.
    if not end_date:
        end_date = datetime.now(timezone.utc).date()
    if not start_date:
        start_date = end_date - timedelta(days=29)

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Região não é campo próprio — é derivada do UF já cadastrado no cliente
    # (Client.state), então o filtro exige join com Client em vez de WHERE direto.
    stmt = (
        select(Order, Client.state)
        .join(Client, Client.id == Order.client_id)
        .where(Order.created_at >= start_dt, Order.created_at <= end_dt)
    )
    if rep_id:
        stmt = stmt.where(Order.rep_id == rep_id)
    rows = (await db.execute(stmt)).all()
    if region:
        rows = [(o, uf) for o, uf in rows if region_for_state(uf) == region]
    orders = [o for o, _ in rows]

    # ── Métricas ────────────────────────────────────────────────────────────
    revenue_total = sum(float(o.total_with_ipi) for o in orders)
    finalized = [o for o in orders if o.is_finalized]
    cancelled = [o for o in orders if o.is_cancelled]
    revenue_finalized = sum(float(o.total_with_ipi) for o in finalized)
    revenue_cancelled = sum(float(o.total_with_ipi) for o in cancelled)
    metrics = DashboardMetrics(
        revenue_total=revenue_total,
        revenue_finalized=revenue_finalized,
        revenue_open=revenue_total - revenue_finalized - revenue_cancelled,
        revenue_cancelled=revenue_cancelled,
        orders_total=len(orders),
        orders_finalized=len(finalized),
        orders_open=len(orders) - len(finalized) - len(cancelled),
        orders_cancelled=len(cancelled),
    )

    # ── Gráfico: granularidade adapta ao tamanho do período (dia/semana/mês) ──
    span_days = (end_date - start_date).days + 1
    granularity = "day" if span_days <= 45 else "week" if span_days <= 180 else "month"
    buckets: dict[str, list[float | int]] = {}
    for o in orders:
        d = o.created_at.date()
        if granularity == "day":
            key = d.isoformat()
        elif granularity == "week":
            key = _week_key(d)
        else:
            key = d.strftime("%Y-%m")
        bucket = buckets.setdefault(key, [0.0, 0])
        bucket[0] += float(o.total_with_ipi)
        bucket[1] += 1
    chart = [
        ChartPoint(key=key, revenue=values[0], orders=int(values[1]))
        for key, values in sorted(buckets.items())
    ]

    # ── Ranking por representante ──────────────────────────────────────────
    rep_ids = {o.rep_id for o in orders if o.rep_id}
    reps_map: dict[uuid.UUID, str] = {}
    if rep_ids:
        reps = (await db.execute(select(Representative).where(Representative.id.in_(rep_ids)))).scalars().all()
        reps_map = {r.id: r.name for r in reps}
    rep_agg: dict[str, list[float | int]] = {}
    for o in orders:
        name = reps_map.get(o.rep_id, "Sem representante") if o.rep_id else "Sem representante"
        bucket = rep_agg.setdefault(name, [0, 0.0])
        bucket[0] += 1
        bucket[1] += float(o.total_with_ipi)
    representatives = sorted(
        (RepresentativeRanking(name=name, orders=int(v[0]), revenue=v[1]) for name, v in rep_agg.items()),
        key=lambda r: r.revenue,
        reverse=True,
    )

    # ── Ranking por produto (itens de todos os pedidos do período) ─────────
    product_agg: dict[str, list] = {}
    for o in orders:
        for item in o.items:
            item_revenue = float(item.qty) * float(item.unit_price) * (1 - float(item.discount) / 100) * (1 + float(item.ipi_rate) / 100)
            bucket = product_agg.setdefault(item.product_code, [item.description, 0, 0.0])
            bucket[1] += item.qty
            bucket[2] += item_revenue
    products = sorted(
        (
            ProductRanking(product_code=code, description=v[0], quantity=int(v[1]), revenue=v[2])
            for code, v in product_agg.items()
        ),
        key=lambda p: p.revenue,
        reverse=True,
    )

    return DashboardOverview(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        metrics=metrics,
        chart=chart,
        representatives=representatives,
        products=products,
    )
