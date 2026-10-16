"""Harness HTTP de integração: PostgreSQL 16 real, AsyncClient/ASGITransport.

Isolamento: cada teste abre conexão dedicada, inicia transação externa e cria
AsyncSession com join_transaction_mode="create_savepoint". Commits das rotas
viram SAVEPOINT/RELEASE — o COMMIT real nunca ocorre. Teardown faz rollback da
transação externa, apagando todos os dados sem truncar tabelas.

get_db_session é sobrescrito em app.dependency_overrides antes de cada teste e
removido no finally — nunca vaza entre testes.

AsyncSession jamais é mockada.
"""
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Define env vars de integração antes de qualquer import de módulo app.

    Executa antes de settings ser instanciado, portanto todas as variáveis
    abaixo são respeitadas pelo Pydantic Settings quando o app é carregado.
    """
    # Permite switch-market em testes: Origin http://testserver passa o guard.
    os.environ.setdefault(
        "BACKEND_CORS_ORIGINS", '["http://testserver","http://localhost:5173"]'
    )
    # DEBUG=true: cookies gerados sem flag Secure, compatível com http://testserver.
    os.environ.setdefault("DEBUG", "true")
    # Rate limiter em memória como fallback local; CI sobrescreve com redis://.
    os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")


def _resolve_db_url() -> str:
    raw = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL", "")
    )
    if not raw:
        raise RuntimeError(
            "Defina TEST_DATABASE_URL ou DATABASE_URL antes de rodar testes de integração."
        )
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Sessão com transação externa por teste; rollback no teardown.

    NullPool garante que cada teste obtém conexão nova no seu próprio loop asyncio,
    evitando o erro "Future attached to a different loop" do asyncpg com pytest-asyncio.
    """
    from app.models.market import Market
    from tests.factories.markets import require_market

    engine = create_async_engine(_resolve_db_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.begin()
            session = AsyncSession(
                conn,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            # Habilitar EU dentro desta transação (revertido pelo rollback).
            await require_market(session, "EU", enabled=True)
            try:
                yield session
            finally:
                await session.close()
                await conn.rollback()
                # Prova pós-rollback: nova conexão confirma que is_enabled voltou ao baseline.
                async with engine.connect() as fresh_conn:
                    fresh_sess = AsyncSession(fresh_conn)
                    try:
                        eu = await fresh_sess.get(Market, "EU")
                        if eu is not None and eu.is_enabled:
                            raise AssertionError(
                                "Rollback pós-teardown não reverteu is_enabled do mercado EU — "
                                "dados de teste vazaram para o banco."
                            )
                    finally:
                        await fresh_sess.close()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    """AsyncClient ASGI com override de get_db_session limpo no teardown."""
    from app.main import app
    from app.api.deps import get_db_session as _dep

    async def _override():
        yield db_session

    app.dependency_overrides[_dep] = _override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(_dep, None)
