import uuid
from datetime import date, datetime, timedelta, timezone

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_principal,
    get_db_session,
    is_client_account,
    require_dashboard_access,
    require_directory_access,
)
from app.core.limiter import limiter
from app.core.search import literal_contains_pattern
from app.core.regions import REGIONS, states_for_region
from app.models.client import Client
from app.models.order import Order, OrderItem
from app.models.representative import Representative
from app.models.user import User, UserRole
from app.schemas.dashboard import (
    ChartPoint,
    ClientContactRow,
    ClientsDashboard,
    DashboardMetrics,
    DashboardOverview,
    ProductRanking,
    RepresentativeRanking,
)
from app.core.markets import MarketPrincipal


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
    # Aba do dashboard: "quotes" = orçamentos (ainda não confirmados, abertos ou
    # cancelados, datados pela criação); "orders" = pedidos (orçamentos
    # confirmados, datados pela confirmação). Ausente = tudo junto (legado).
    kind: Literal["quotes", "orders"] | None = Query(default=None),
    ranking_limit: int = Query(default=100, ge=5, le=500),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_dashboard_access),
    principal: MarketPrincipal = Depends(get_current_principal),
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
    date_column = Order.finalized_at if kind == "orders" else Order.created_at
    conditions = [
        Order.market_code == principal.code,
        date_column >= start_dt,
        date_column < end_exclusive,
    ]
    if kind == "quotes":
        conditions.append(Order.is_finalized.is_(False))
    elif kind == "orders":
        conditions.append(Order.is_finalized.is_(True))
    if current_user.role == UserRole.representante:
        conditions.append(
            Order.rep_id == current_user.rep_id
            if current_user.rep_id is not None
            else false()
        )
    elif is_client_account(current_user):
        conditions.append(
            Order.client_id == current_user.linked_id
            if current_user.linked_id is not None
            else false()
        )
    elif rep_id:
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
    delivered_condition = and_(
        Order.is_finalized.is_(True),
        Order.order_stage == "delivered",
    )
    # Pedido sem etapa gravada conta como "em produção" (mesma regra do app).
    production_condition = and_(
        Order.is_finalized.is_(True),
        Order.order_stage.is_distinct_from("delivered"),
    )
    metrics_stmt = filtered(
        select(
            func.coalesce(
                func.sum(case(
                    (Order.is_cancelled.is_(False), Order.total_with_ipi),
                    else_=0,
                )),
                0,
            ).label("revenue_total"),
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
            func.coalesce(
                func.sum(case((production_condition, Order.total_with_ipi), else_=0)),
                0,
            ).label("revenue_production"),
            func.coalesce(
                func.sum(case((delivered_condition, Order.total_with_ipi), else_=0)),
                0,
            ).label("revenue_delivered"),
            func.count(Order.id).filter(production_condition).label("orders_production"),
            func.count(Order.id).filter(delivered_condition).label("orders_delivered"),
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
        revenue_production=float(metrics_row.revenue_production),
        revenue_delivered=float(metrics_row.revenue_delivered),
        orders_production=int(metrics_row.orders_production),
        orders_delivered=int(metrics_row.orders_delivered),
    )

    span_days = (end_date - start_date).days + 1
    granularity = "day" if span_days <= 45 else "week" if span_days <= 180 else "month"
    bucket = func.date_trunc(
        granularity,
        func.timezone("UTC", date_column),
    ).label("bucket")
    chart_stmt = filtered(
        select(
            bucket,
            func.coalesce(func.sum(Order.total_with_ipi), 0).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .select_from(Order)
        .where(Order.is_cancelled.is_(False))
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
        .where(Order.is_cancelled.is_(False))
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
        .where(Order.is_cancelled.is_(False))
        .group_by(OrderItem.product_code)
        .order_by(func.sum(item_revenue).desc())
        .limit(ranking_limit)
    )
    products = [
        ProductRanking(
            product_code=row.product_code,
            description=row.description,
            # Tapete soma m² com 2 casas; inteiro truncaria 4,5 m² para 4.
            quantity=float(row.quantity),
            revenue=float(row.revenue),
        )
        for row in (await db.execute(products_stmt)).all()
    ]

    return DashboardOverview(
        kind=kind,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        metrics=metrics,
        chart=chart,
        representatives=representatives,
        products=products,
    )


@router.get("/clients", response_model=ClientsDashboard)
@limiter.limit("30/minute")
async def get_clients_dashboard(
    request: Request,
    response: Response,
    contacted: Literal["all", "yes", "no"] = Query(default="all"),
    q: str | None = Query(default=None, max_length=200),
    skip: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_directory_access),
    principal: MarketPrincipal = Depends(get_current_principal),
):
    """Dashboard de Clientes: quem já foi contactado e quem ainda não.

    Mesmo escopo da listagem de clientes: representante só enxerga a própria
    carteira, admin e operadores internos o mercado inteiro, e conta de cliente
    não tem acesso. Os contadores vêm do servidor, sobre a carteira inteira do
    usuário (sem depender do filtro ou da busca da lista).
    """
    if is_client_account(current_user):
        raise HTTPException(
            status_code=403, detail="Operação não permitida para o seu nível de acesso."
        )
    # "Cliente contactado" só existe na ficha de Portugal; no Brasil o campo é
    # descartado no cadastro, então o indicador não faria sentido.
    if principal.code != "EU":
        raise HTTPException(
            status_code=404,
            detail="Dashboard de clientes disponível apenas no mercado Portugal.",
        )

    scope = [Client.market_code == principal.code]
    if current_user.role == UserRole.representante:
        scope.append(
            Client.rep_id == current_user.rep_id
            if current_user.rep_id is not None
            else false()
        )

    counts = (
        await db.execute(
            select(
                func.count(Client.id).label("total"),
                func.count(Client.id).filter(Client.contacted.is_(True)).label("contacted"),
            )
            .select_from(Client)
            .where(*scope)
        )
    ).one()
    total = int(counts.total)
    contacted_count = int(counts.contacted)

    filters = list(scope)
    if contacted == "yes":
        filters.append(Client.contacted.is_(True))
    elif contacted == "no":
        filters.append(Client.contacted.is_(False))
    search = q.strip() if q else ""
    if search:
        pattern = literal_contains_pattern(search)
        filters.append(
            or_(
                Client.name.ilike(pattern, escape="\\"),
                Client.contact_name.ilike(pattern, escape="\\"),
                Client.email.ilike(pattern, escape="\\"),
            )
        )

    filtered_total = (
        await db.execute(select(func.count()).select_from(Client).where(*filters))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Client, Representative.name.label("rep_name"))
            .outerjoin(Representative, Representative.id == Client.rep_id)
            .where(*filters)
            .order_by(Client.contacted.asc(), func.lower(Client.name).asc(), Client.id.asc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    items = [
        ClientContactRow(
            id=client.id,
            name=client.name,
            contact_name=client.contact_name,
            phone=client.phone,
            email=client.email,
            city=client.city,
            country=client.country,
            rep_id=client.rep_id,
            rep_name=rep_name,
            contacted=bool(client.contacted),
        )
        for client, rep_name in rows
    ]
    return ClientsDashboard(
        total=total,
        contacted=contacted_count,
        not_contacted=total - contacted_count,
        contacted_pct=round(contacted_count / total * 100, 1) if total else 0.0,
        filtered_total=int(filtered_total),
        items=items,
    )
