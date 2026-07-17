import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_dashboard_access
from app.core.limiter import limiter
from app.core.regions import REGIONS, states_for_region
from app.models.client import Client
from app.models.order import Order, OrderItem
from app.models.representative import Representative
from app.models.user import User
from app.schemas.dashboard import (
    ChartPoint,
    DashboardMetrics,
    DashboardOverview,
    ProductRanking,
    RepresentativeRanking,
)


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _format_bucket(bucket: datetime, granularity: str) -> str:
    if granularity == "month":
        return bucket.strftime("%Y-%m")
    return bucket.date().isoformat()


@router.get("/overview", response_model=DashboardOverview)
@limiter.limit("30/minute")
async def get_overview(
    request: Request,
    response: Response,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    rep_id: uuid.UUID | None = Query(default=None),
    region: str | None = Query(default=None),
    ranking_limit: int = Query(default=100, ge=5, le=500),
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_dashboard_access),
):
    if not end_date:
        end_date = datetime.now(timezone.utc).date()
    if not start_date:
        start_date = end_date - timedelta(days=29)
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="Data inicial não pode ser posterior à data final.",
        )
    if region and region not in REGIONS:
        raise HTTPException(status_code=422, detail="Região inválida.")

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_exclusive = datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    conditions = [
        Order.created_at >= start_dt,
        Order.created_at < end_exclusive,
    ]
    if rep_id:
        conditions.append(Order.rep_id == rep_id)
    region_states = states_for_region(region) if region else None

    def filtered(stmt):
        stmt = stmt.where(*conditions)
        if region_states is not None:
            stmt = stmt.join(Client, Client.id == Order.client_id).where(
                Client.state.in_(region_states)
            )
        return stmt

    open_condition = and_(
        Order.is_finalized.is_(False),
        Order.is_cancelled.is_(False),
    )
    metrics_stmt = filtered(
        select(
            func.coalesce(func.sum(Order.total_with_ipi), 0).label("revenue_total"),
            func.coalesce(
                func.sum(
                    case(
                        (Order.is_finalized.is_(True), Order.total_with_ipi),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue_finalized"),
            func.coalesce(
                func.sum(
                    case(
                        (open_condition, Order.total_with_ipi),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue_open"),
            func.coalesce(
                func.sum(
                    case(
                        (Order.is_cancelled.is_(True), Order.total_with_ipi),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue_cancelled"),
            func.count(Order.id).label("orders_total"),
            func.count(Order.id)
            .filter(Order.is_finalized.is_(True))
            .label("orders_finalized"),
            func.count(Order.id).filter(open_condition).label("orders_open"),
            func.count(Order.id)
            .filter(Order.is_cancelled.is_(True))
            .label("orders_cancelled"),
        ).select_from(Order)
    )
    metrics_row = (await db.execute(metrics_stmt)).one()
    metrics = DashboardMetrics(
        revenue_total=float(metrics_row.revenue_total),
        revenue_finalized=float(metrics_row.revenue_finalized),
        revenue_open=float(metrics_row.revenue_open),
        revenue_cancelled=float(metrics_row.revenue_cancelled),
        orders_total=int(metrics_row.orders_total),
        orders_finalized=int(metrics_row.orders_finalized),
        orders_open=int(metrics_row.orders_open),
        orders_cancelled=int(metrics_row.orders_cancelled),
    )

    span_days = (end_date - start_date).days + 1
    granularity = "day" if span_days <= 45 else "week" if span_days <= 180 else "month"
    bucket = func.date_trunc(
        granularity,
        func.timezone("UTC", Order.created_at),
    ).label("bucket")
    chart_stmt = filtered(
        select(
            bucket,
            func.coalesce(func.sum(Order.total_with_ipi), 0).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .select_from(Order)
        .group_by(bucket)
        .order_by(bucket)
    )
    chart = [
        ChartPoint(
            key=_format_bucket(row.bucket, granularity),
            revenue=float(row.revenue),
            orders=int(row.orders),
        )
        for row in (await db.execute(chart_stmt)).all()
    ]

    rep_name = func.coalesce(Representative.name, "Sem representante").label("name")
    reps_stmt = filtered(
        select(
            Order.rep_id,
            rep_name,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_with_ipi), 0).label("revenue"),
        )
        .select_from(Order)
        .outerjoin(Representative, Representative.id == Order.rep_id)
        .group_by(Order.rep_id, Representative.name)
        .order_by(func.sum(Order.total_with_ipi).desc())
        .limit(ranking_limit)
    )
    representatives = [
        RepresentativeRanking(
            name=row.name,
            orders=int(row.orders),
            revenue=float(row.revenue),
        )
        for row in (await db.execute(reps_stmt)).all()
    ]

    discounted_subtotal = (
        OrderItem.qty
        * OrderItem.unit_price
        * (1 - OrderItem.discount / 100)
    )
    item_revenue = discounted_subtotal + OrderItem.ipi_value
    products_stmt = filtered(
        select(
            OrderItem.product_code,
            func.max(OrderItem.description).label("description"),
            func.coalesce(func.sum(OrderItem.qty), 0).label("quantity"),
            func.coalesce(func.sum(item_revenue), 0).label("revenue"),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .group_by(OrderItem.product_code)
        .order_by(func.sum(item_revenue).desc())
        .limit(ranking_limit)
    )
    products = [
        ProductRanking(
            product_code=row.product_code,
            description=row.description,
            quantity=int(row.quantity),
            revenue=float(row.revenue),
        )
        for row in (await db.execute(products_stmt)).all()
    ]

    return DashboardOverview(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        metrics=metrics,
        chart=chart,
        representatives=representatives,
        products=products,
    )
