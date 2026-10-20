"""Testes de integração: saúde da API, autenticação e prova de isolamento.

Cobre:
- /health/live  — liveness sem banco
- /health/ready — readiness prova conexão real ao PostgreSQL
- POST /api/v1/auth/login — login persiste RefreshToken; verificado via SELECT
- GET  /api/v1/auth/me   — retorna mercado e papel corretos
- isolamento: dados visíveis dentro da transação, invisíveis em conexão nova
"""
import os

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine

from app.models.refresh_token import RefreshToken
from tests.factories import make_user, make_user_market

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _resolve_url() -> str:
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw


async def test_health_live(client: AsyncClient) -> None:
    """GET /health/live deve retornar 200 sem acessar o banco."""
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_health_ready_proves_real_db(client: AsyncClient) -> None:
    """/health/ready usa AsyncSessionLocal (engine da app) — prova PostgreSQL real."""
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


async def test_login_writes_refresh_token_to_real_db(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Login cria RefreshToken no PostgreSQL real; SELECT no banco confirma a gravação."""
    user = await make_user(db_session, email="login-test@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="admin")
    user_id = user.id
    await db_session.flush()

    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "login-test@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("access_token"), "Sem access_token na resposta"

    # Prova de escrita: SELECT no banco dentro da mesma transação externa.
    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.scope == "market",
            RefreshToken.revoked.is_(False),
        )
    )
    token_row = result.scalar_one_or_none()
    assert token_row is not None, "RefreshToken não encontrado no banco após login"
    assert token_row.active_market == "BR"


async def test_auth_me_returns_market_and_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /auth/me devolve mercado ativo e papel do vínculo — PostgreSQL real."""
    user = await make_user(db_session, email="me-test@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="vendedor")
    await db_session.flush()

    login_r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "me-test@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert login_r.status_code == 200, login_r.text
    token = login_r.json()["access_token"]

    me_r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_r.status_code == 200, me_r.text
    me = me_r.json()
    assert me["active_market"] == "BR"
    assert me["role"] == "vendedor"
    assert "EU" not in me.get("allowed_markets", [])


async def test_isolation_rollback_is_observable(
    db_session: AsyncSession,
) -> None:
    """Sentinel EU is_enabled=False→True: visível na transação, invisível externamente.

    O fixture db_session habilita EU no início de cada teste (dentro da transação
    externa). Este teste verifica as duas primeiras provas:

    1. Dentro de db_session: is_enabled=True.
    2. Conexão externa independente: is_enabled=False (transação não commitada).

    A terceira prova — is_enabled reverte após conn.rollback() no teardown —
    é executada automaticamente pelo fixture em conftest.py, cobrindo também os
    savepoints emitidos por rotas HTTP (login, switch-market).
    """
    from app.models.market import Market

    # Prova 1: sentinel visível dentro da transação.
    eu_in = await db_session.get(Market, "EU")
    assert eu_in is not None
    assert eu_in.is_enabled is True, "EU deveria estar habilitado dentro da transação"

    # Prova 2: sentinel invisível numa conexão completamente independente.
    engine2: AsyncEngine = create_async_engine(_resolve_url(), pool_size=1)
    try:
        async with engine2.connect() as conn2:
            sess2 = AsyncSession(conn2)
            try:
                eu_ext = await sess2.get(Market, "EU")
                assert eu_ext is not None
                assert eu_ext.is_enabled is False, (
                    "is_enabled=True vazou para conexão externa — transação não isolada."
                )
            finally:
                await sess2.close()
    finally:
        await engine2.dispose()
