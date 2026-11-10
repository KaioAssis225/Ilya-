"""Dashboard: abas Orçamentos/Pedidos e dashboard de Clientes (contactados).

Roda contra PostgreSQL real. Cobre a separação orçamento × pedido no
`/dashboard/overview?kind=`, o `/dashboard/clients` (contadores, filtros e busca
feitos no servidor) e o RBAC + ownership da carteira.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.market import PriceList
from app.models.user import UserRole
from tests.factories import (
    make_client,
    make_representative,
    make_user,
    make_user_market,
)
from tests.factories.orders import make_order

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _token(
    db: AsyncSession,
    role: UserRole,
    market: str = "EU",
    *,
    rep_id: uuid.UUID | None = None,
    linked_client_id: uuid.UUID | None = None,
    can_view_dashboard: bool = False,
) -> str:
    user = await make_user(
        db,
        email=f"dash-{role.value}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=role,
        home_market=market,
    )
    if linked_client_id is not None:
        user.linked_id = linked_client_id
    membership = await make_user_market(
        db,
        user,
        market_code=market,
        role=role.value,
        rep_id=rep_id,
        linked_client_id=linked_client_id,
    )
    if can_view_dashboard:
        user.can_view_dashboard = True
        membership.can_view_dashboard = True
    await db.flush()
    return create_access_token(user.id, role.value, user.auth_version, market)


async def _eu_client(db: AsyncSession, name: str, **fields):
    price_list = (
        await db.execute(
            select(PriceList).where(PriceList.market_code == "EU", PriceList.code == "lojista")
        )
    ).scalar_one()
    client = await make_client(db, price_list, market_code="EU", name=name)
    for key, value in fields.items():
        setattr(client, key, value)
    await db.flush()
    return client


async def _order(
    db: AsyncSession,
    client,
    *,
    total: str,
    finalized: bool = False,
    cancelled: bool = False,
    stage: str | None = None,
    rep_id: uuid.UUID | None = None,
    finalized_at: datetime | None = None,
):
    # Dono de numeração próprio por pedido: evita colidir no número sequencial.
    order = await make_order(db, client, uuid.uuid4())
    order.total_with_ipi = Decimal(total)
    order.rep_id = rep_id
    now = datetime.now(timezone.utc)
    if finalized:
        order.is_finalized = True
        order.finalized_at = finalized_at or now
        order.order_stage = stage or "production"
        if order.order_stage == "delivered":
            order.delivered_at = now
    if cancelled:
        order.is_cancelled = True
        order.cancelled_at = now
    await db.flush()
    return order


def _window() -> dict:
    today = datetime.now(timezone.utc).date()
    return {
        "start_date": (today - timedelta(days=2)).isoformat(),
        "end_date": (today + timedelta(days=1)).isoformat(),
    }


async def _overview(client: AsyncClient, token: str, **params):
    return await client.get(
        "/api/v1/dashboard/overview", params={**_window(), **params}, headers=_auth(token)
    )


# ── Abas Orçamentos × Pedidos ────────────────────────────────────────────────


async def _seed_orders(db: AsyncSession):
    cliente = await _eu_client(db, "Cliente Abas")
    await _order(db, cliente, total="100.00")  # orçamento em aberto
    await _order(db, cliente, total="40.00", cancelled=True)  # orçamento cancelado
    await _order(db, cliente, total="500.00", finalized=True, stage="production")
    await _order(db, cliente, total="300.00", finalized=True, stage="delivered")
    return cliente


async def test_quotes_tab_only_counts_unconfirmed_quotes(client, db_session):
    await _seed_orders(db_session)
    admin = await _token(db_session, UserRole.admin)

    response = await _overview(client, admin, kind="quotes")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "quotes"
    metrics = body["metrics"]
    assert metrics["orders_total"] == 2  # aberto + cancelado; pedidos ficam fora
    assert metrics["orders_open"] == 1
    assert metrics["orders_cancelled"] == 1
    assert metrics["orders_finalized"] == 0
    assert metrics["revenue_total"] == 100.0  # cancelado não soma
    assert metrics["revenue_open"] == 100.0
    assert metrics["revenue_cancelled"] == 40.0


async def test_orders_tab_only_counts_confirmed_orders_by_stage(client, db_session):
    await _seed_orders(db_session)
    admin = await _token(db_session, UserRole.admin)

    response = await _overview(client, admin, kind="orders")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "orders"
    metrics = body["metrics"]
    assert metrics["orders_total"] == 2  # só os confirmados
    assert metrics["orders_production"] == 1
    assert metrics["orders_delivered"] == 1
    assert metrics["revenue_total"] == 800.0
    assert metrics["revenue_production"] == 500.0
    assert metrics["revenue_delivered"] == 300.0
    assert metrics["orders_open"] == 0
    assert metrics["orders_cancelled"] == 0
    assert sum(point["orders"] for point in body["chart"]) == 2


async def test_orders_tab_is_dated_by_confirmation_not_creation(client, db_session):
    cliente = await _eu_client(db_session, "Cliente Data")
    old = datetime.now(timezone.utc) - timedelta(days=60)
    await _order(db_session, cliente, total="70.00", finalized=True, finalized_at=old)
    admin = await _token(db_session, UserRole.admin)

    # Criado agora, confirmado há 60 dias: fora da janela de confirmação.
    metrics = (await _overview(client, admin, kind="orders")).json()["metrics"]
    assert metrics["orders_total"] == 0


async def test_overview_without_kind_keeps_legacy_totals(client, db_session):
    await _seed_orders(db_session)
    admin = await _token(db_session, UserRole.admin)

    body = (await _overview(client, admin)).json()

    assert body["kind"] is None
    assert body["metrics"]["orders_total"] == 4


async def test_overview_rejects_unknown_kind(client, db_session):
    admin = await _token(db_session, UserRole.admin)
    response = await _overview(client, admin, kind="tudo")
    assert response.status_code == 422


async def test_overview_tabs_keep_representative_ownership(client, db_session):
    rep_a = await make_representative(db_session, market_code="EU", name="Rep A")
    rep_b = await make_representative(db_session, market_code="EU", name="Rep B")
    cliente = await _eu_client(db_session, "Cliente Carteira", rep_id=rep_a.id)
    await _order(db_session, cliente, total="10.00", rep_id=rep_a.id)
    await _order(db_session, cliente, total="20.00", rep_id=rep_b.id)
    await _order(db_session, cliente, total="30.00", rep_id=rep_b.id, finalized=True)
    token_a = await _token(
        db_session, UserRole.representante, rep_id=rep_a.id, can_view_dashboard=True
    )

    quotes = (await _overview(client, token_a, kind="quotes")).json()["metrics"]
    orders = (await _overview(client, token_a, kind="orders")).json()["metrics"]

    assert quotes["orders_total"] == 1
    assert quotes["revenue_total"] == 10.0
    assert orders["orders_total"] == 0


# ── Dashboard de Clientes ────────────────────────────────────────────────────


async def _seed_portfolio(db: AsyncSession):
    rep_a = await make_representative(db, market_code="EU", name="Rep Alfa")
    rep_b = await make_representative(db, market_code="EU", name="Rep Beta")
    await _eu_client(db, "Alfa Contactado", rep_id=rep_a.id, contacted=True, contact_name="Ana")
    await _eu_client(db, "Alfa Pendente", rep_id=rep_a.id, contacted=False)
    await _eu_client(db, "Beta Contactado", rep_id=rep_b.id, contacted=True)
    await _eu_client(db, "Beta Pendente", rep_id=rep_b.id, contacted=False)
    await _eu_client(db, "Sem Rep", contacted=False)
    return rep_a, rep_b


async def _clients(client: AsyncClient, token: str, **params):
    return await client.get(
        "/api/v1/dashboard/clients", params=params, headers=_auth(token)
    )


async def test_clients_dashboard_admin_sees_whole_market(client, db_session):
    await _seed_portfolio(db_session)
    admin = await _token(db_session, UserRole.admin)

    response = await _clients(client, admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 5
    assert body["contacted"] == 2
    assert body["not_contacted"] == 3
    assert body["contacted_pct"] == 40.0
    assert body["filtered_total"] == 5
    names = [item["name"] for item in body["items"]]
    # Não contactados primeiro (quem falta contactar), depois por nome.
    assert names == ["Alfa Pendente", "Beta Pendente", "Sem Rep", "Alfa Contactado", "Beta Contactado"]
    alfa = next(item for item in body["items"] if item["name"] == "Alfa Contactado")
    assert alfa["contacted"] is True
    assert alfa["contact_name"] == "Ana"
    assert alfa["rep_name"] == "Rep Alfa"


async def test_clients_dashboard_filters_and_search_run_on_server(client, db_session):
    await _seed_portfolio(db_session)
    admin = await _token(db_session, UserRole.admin)

    yes = (await _clients(client, admin, contacted="yes")).json()
    no = (await _clients(client, admin, contacted="no")).json()
    search = (await _clients(client, admin, q="beta")).json()

    assert {item["name"] for item in yes["items"]} == {"Alfa Contactado", "Beta Contactado"}
    assert yes["filtered_total"] == 2
    assert no["filtered_total"] == 3
    assert all(item["contacted"] is False for item in no["items"])
    # Os contadores não mudam com o filtro nem com a busca.
    assert (yes["total"], yes["contacted"]) == (5, 2)
    assert (search["total"], search["contacted"]) == (5, 2)
    assert {item["name"] for item in search["items"]} == {"Beta Contactado", "Beta Pendente"}


async def test_clients_dashboard_paginates(client, db_session):
    await _seed_portfolio(db_session)
    admin = await _token(db_session, UserRole.admin)

    page = (await _clients(client, admin, limit=2, skip=2)).json()

    assert page["filtered_total"] == 5
    assert len(page["items"]) == 2


async def test_clients_dashboard_representative_only_sees_own_portfolio(client, db_session):
    rep_a, rep_b = await _seed_portfolio(db_session)
    token_a = await _token(db_session, UserRole.representante, rep_id=rep_a.id)

    body = (await _clients(client, token_a)).json()

    assert body["total"] == 2
    assert body["contacted"] == 1
    assert {item["name"] for item in body["items"]} == {"Alfa Contactado", "Alfa Pendente"}
    # Nada da carteira do outro representante vaza, nem pela busca.
    leaked = (await _clients(client, token_a, q="Beta")).json()
    assert leaked["items"] == []
    assert leaked["total"] == 2
    token_b = await _token(db_session, UserRole.representante, rep_id=rep_b.id)
    assert (await _clients(client, token_b)).json()["total"] == 2


async def test_clients_dashboard_denies_client_accounts(client, db_session):
    cliente = await _eu_client(db_session, "Conta Cliente")
    token = await _token(db_session, UserRole.cliente, linked_client_id=cliente.id)

    response = await _clients(client, token)

    assert response.status_code == 403


async def test_clients_dashboard_denies_executive_and_anonymous(client, db_session):
    executivo = await _token(db_session, UserRole.executivo)

    assert (await _clients(client, executivo)).status_code == 403
    anonymous = await client.get("/api/v1/dashboard/clients")
    assert anonymous.status_code in (401, 403)


async def test_clients_dashboard_is_portugal_only(client, db_session):
    admin_br = await _token(db_session, UserRole.admin, market="BR")

    response = await _clients(client, admin_br)

    assert response.status_code == 404


async def test_clients_dashboard_ignores_other_market(client, db_session):
    await _seed_portfolio(db_session)
    admin = await _token(db_session, UserRole.admin)
    before = (await _clients(client, admin)).json()["total"]

    br_price_list = (
        await db_session.execute(
            select(PriceList).where(PriceList.market_code == "BR", PriceList.code == "lojista")
        )
    ).scalar_one()
    await make_client(db_session, br_price_list, market_code="BR", name="Cliente Brasil")
    await db_session.flush()

    assert (await _clients(client, admin)).json()["total"] == before
