"""Testes de isolamento multimercado BR/EU.

Cobre ISO-01, ISO-03, ISO-04, ISO-05, ISO-12, ISO-23 conforme
docs/TESTES-ISOLAMENTO-MULTIMERCADO.md.

ISO-01  login real + switch-market → 403 quando sem vínculo EU; prova que
        nenhum token EU foi emitido (SELECT RefreshToken).
ISO-03  representante EU real; login + switch-market → papel adotado do novo
        mercado, não do mercado original.
ISO-04  plataforma sem UserMarket não obtém sessão comercial; token de
        plataforma rejeitado em rota comercial.
ISO-05  admin comercial BR tenta POST /api/v1/markets/EU/activate com token de
        mercado → 401 (scope=market rejeitado antes do gate de capacidade; spec
        prevê 403 — divergência documentada em docs/TESTING.md §2).
        Complementar: read_outbox sem activate_market → 403 capability gate.
ISO-12  UUID de cliente EU retorna 404 em sessão BR.
ISO-23  mutação autorizada (PATCH cliente BR) grava no banco; mutação negada
        (PATCH cliente EU) retorna 404 e deixa o cliente EU inalterado.

Sem mock de AsyncSession — PostgreSQL real em todos os testes.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.market import Market
from app.models.refresh_token import RefreshToken
from tests.factories import (
    make_client,
    make_platform_permission,
    make_price_list,
    make_representative,
    make_user,
    make_user_market,
)
from tests.factories.orders import make_order

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# Cabeçalho de origem confiável — mesma entrada em BACKEND_CORS_ORIGINS do CI
# e do pytest_configure da integração.
_TRUSTED_ORIGIN = {"Origin": "http://testserver"}


# ── ISO-01 ─────────────────────────────────────────────────────────────────────

async def test_iso01_switch_to_eu_denied_without_market_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-01: sessão real → switch-market BR→EU → 403; nenhum token EU emitido.

    Prova: SELECT em refresh_tokens confirma ausência de ativo_mercado='EU'.
    """
    user = await make_user(db_session, email="iso01@ilya-test.invalid", home_market="BR")
    await make_user_market(db_session, user, market_code="BR", role="admin")
    await db_session.flush()

    login_r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "iso01@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert login_r.status_code == 200, login_r.text
    access_token = login_r.json()["access_token"]

    switch_r = await client.post(
        "/api/v1/auth/switch-market",
        json={"market": "EU"},
        headers={"Authorization": f"Bearer {access_token}", **_TRUSTED_ORIGIN},
    )
    assert switch_r.status_code == 403, switch_r.text

    # Prova: nenhum RefreshToken com active_market=EU foi criado.
    eu_tokens = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.active_market == "EU",
        )
    )).scalars().all()
    assert len(eu_tokens) == 0, "Nenhum token EU deve ser emitido para conta sem vínculo EU"


# ── ISO-03 ─────────────────────────────────────────────────────────────────────

async def test_iso03_switch_market_adopts_target_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-03: mesma identidade; switch-market adota papel do vínculo de destino.

    vendedor BR + representante EU (com Representative real): após troca, o
    token devolve papel do vínculo EU, não o BR.
    """
    eu_rep = await make_representative(db_session, market_code="EU")
    user = await make_user(db_session, email="iso03@ilya-test.invalid", home_market="BR")
    await make_user_market(db_session, user, market_code="BR", role="vendedor")
    await make_user_market(
        db_session, user, market_code="EU", role="representante", rep_id=eu_rep.id
    )
    await db_session.flush()

    login_r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "iso03@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert login_r.status_code == 200
    br_token = login_r.json()["access_token"]

    # Sessão BR: papel deve ser vendedor
    me_br = (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {br_token}"})
    ).json()
    assert me_br["role"] == "vendedor"
    assert me_br["active_market"] == "BR"

    # Trocar para EU
    switch_r = await client.post(
        "/api/v1/auth/switch-market",
        json={"market": "EU"},
        headers={"Authorization": f"Bearer {br_token}", **_TRUSTED_ORIGIN},
    )
    assert switch_r.status_code == 200, switch_r.text
    eu_token = switch_r.json()["access_token"]

    # Sessão EU: papel deve ser representante (do vínculo EU), não vendedor
    me_eu = (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {eu_token}"})
    ).json()
    assert me_eu["role"] == "representante", (
        f"Papel EU esperado: representante; recebido: {me_eu['role']}"
    )
    assert me_eu["active_market"] == "EU"

    # Resíduo: exactamente 1 RefreshToken ativo com active_market=EU; sem extras.
    # switch-market muta o token existente (active_market BR→EU) sem criar novo.
    active_tokens = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.scope == "market",
            RefreshToken.revoked.is_(False),
        )
    )).scalars().all()
    assert len(active_tokens) == 1, (
        f"Esperado 1 token ativo após switch; encontrado {len(active_tokens)}"
    )
    assert active_tokens[0].active_market == "EU", (
        f"Token ativo deve ter active_market=EU; era {active_tokens[0].active_market!r}"
    )


# ── ISO-04 ─────────────────────────────────────────────────────────────────────

async def test_iso04_platform_only_user_cannot_login_commercially(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-04: identidade somente de plataforma não obtém sessão comercial."""
    user = await make_user(db_session, email="iso04@ilya-test.invalid")
    await make_platform_permission(db_session, user, capability="platform_admin")
    await db_session.flush()

    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "iso04@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert r.status_code == 403, r.text

    # Ausência de resíduo: login negado não deve ter criado RefreshToken de mercado.
    market_tokens = (await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.scope == "market",
        )
    )).scalars().all()
    assert len(market_tokens) == 0, "Login negado não deve criar RefreshToken de mercado"


async def test_iso04_platform_token_rejected_on_commercial_route(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-04 (variante): scope=platform é inválido em rota comercial → 401."""
    user = await make_user(db_session, email="iso04b@ilya-test.invalid")
    await make_platform_permission(db_session, user, capability="platform_admin")
    await db_session.flush()

    platform_token = create_access_token(
        user.id, None, user.auth_version, None, scope="platform"
    )
    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert r.status_code == 401, r.text


# ── ISO-05 ─────────────────────────────────────────────────────────────────────

async def test_iso05_commercial_user_cannot_activate_market(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-05 principal: admin comercial BR tenta ativar EU com token de mercado → 401.

    POST /api/v1/markets/EU/activate usa require_platform_capability, que chama
    get_platform_principal. Esse guard rejeita qualquer token sem scope=platform
    com 401 — o gate de capacidade nem chega a ser avaliado.

    DIVERGÊNCIA documentada: o documento de especificação TESTES-ISOLAMENTO-
    MULTIMERCADO.md prevê 403 para este ator. O contrato real do endpoint
    retorna 401. Conforme docs/TESTING.md §2, o contrato real prevalece; a
    regra de negócio NÃO foi alterada para adequar o teste.

    Ausência de resíduo: EU is_enabled permanece True (valor do fixture),
    confirmando que a tentativa negada não alterou o banco.
    """
    user = await make_user(db_session, email="iso05-main@ilya-test.invalid", home_market="BR")
    await make_user_market(db_session, user, market_code="BR", role="admin")
    await db_session.flush()

    login_r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "iso05-main@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert login_r.status_code == 200, login_r.text
    market_token = login_r.json()["access_token"]

    activate_r = await client.post(
        "/api/v1/markets/EU/activate",
        headers={"Authorization": f"Bearer {market_token}"},
    )
    # 401: scope=market rejeitado por get_platform_principal antes do capability gate.
    # Divergência vs spec (403) documentada em docs/TESTING.md §2.
    assert activate_r.status_code == 401, activate_r.text

    # Ausência de resíduo: Market EU inalterado.
    eu_market = await db_session.get(Market, "EU")
    assert eu_market is not None and eu_market.is_enabled is True, (
        "Market EU não deveria ter sido alterado pela tentativa negada"
    )


async def test_platform_capability_gate_read_outbox_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Complementar ISO-05: capability gate real — read_outbox → 403 em /activate.

    Diferente do teste principal (scope=market → 401), aqui o token tem
    scope=platform mas a capability read_outbox não inclui activate_market →
    require_platform_capability("activate_market") devolve 403.
    Exercita o gate de capacidade (não apenas o gate de escopo).
    """
    user = await make_user(db_session, email="iso05-cap@ilya-test.invalid")
    await make_platform_permission(db_session, user, capability="read_outbox")
    await db_session.flush()

    platform_login_r = await client.post(
        "/api/v1/platform/auth/login",
        json={"identifier": "iso05-cap@ilya-test.invalid", "password": "TestPassword1"},
    )
    assert platform_login_r.status_code == 200, platform_login_r.text
    platform_token = platform_login_r.json()["access_token"]

    activate_r = await client.post(
        "/api/v1/markets/EU/activate",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert activate_r.status_code == 403, activate_r.text

    # Ausência de resíduo: Market EU is_enabled permanece True (estado do fixture).
    eu_market = await db_session.get(Market, "EU")
    assert eu_market is not None and eu_market.is_enabled is True, (
        "Market EU não deveria ter sido alterado pela tentativa negada (read_outbox)"
    )


# ── ISO-12 ─────────────────────────────────────────────────────────────────────

async def test_iso12_eu_client_uuid_invisible_from_br_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-12: GET cliente EU por UUID retorna 404 em sessão BR."""
    user = await make_user(db_session, email="iso12@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="vendedor")
    eu_pl = await make_price_list(db_session, market_code="EU")
    eu_client = await make_client(db_session, eu_pl, market_code="EU", name="ISO-12 EU Client")
    await db_session.flush()

    br_token = create_access_token(user.id, "vendedor", user.auth_version, "BR")
    r = await client.get(
        f"/api/v1/clients/{eu_client.id}",
        headers={"Authorization": f"Bearer {br_token}"},
    )
    assert r.status_code == 404, r.text


# ── ISO-23 ─────────────────────────────────────────────────────────────────────

async def test_iso23_eu_order_uuid_invisible_from_br_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-23: GET pedido EU por UUID retorna 404 em sessão BR."""
    user = await make_user(db_session, email="iso23@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="vendedor")
    eu_pl = await make_price_list(db_session, market_code="EU")
    eu_client = await make_client(db_session, eu_pl, market_code="EU", name="ISO-23 EU Client")
    eu_order = await make_order(db_session, eu_client, user.id)
    await db_session.flush()

    br_token = create_access_token(user.id, "vendedor", user.auth_version, "BR")
    r = await client.get(
        f"/api/v1/orders/{eu_order.id}",
        headers={"Authorization": f"Bearer {br_token}"},
    )
    assert r.status_code == 404, r.text


async def test_iso23_br_order_readable_from_br_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-23 (controlo positivo): pedido BR acessível em sessão BR — sem falso positivo."""
    user = await make_user(db_session, email="iso23ok@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="admin")
    br_pl = await make_price_list(db_session, market_code="BR")
    br_client = await make_client(db_session, br_pl, market_code="BR", name="ISO-23 BR Client")
    br_order = await make_order(db_session, br_client, user.id)
    await db_session.flush()

    br_token = create_access_token(user.id, "admin", user.auth_version, "BR")
    r = await client.get(
        f"/api/v1/orders/{br_order.id}",
        headers={"Authorization": f"Bearer {br_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(br_order.id)


async def test_iso23_authorized_mutation_writes_to_db_denied_leaves_no_residue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-23 — mutação autorizada + negada + ausência de resíduo.

    1. PATCH de cliente BR com admin BR → 200; SELECT no banco confirma escrita.
    2. PATCH de cliente EU com token BR → 404; SELECT com skip_market_scope
       confirma que o cliente EU está inalterado (phone original preservado).
    """
    from app.models.client import Client

    user = await make_user(db_session, email="iso23-mut@ilya-test.invalid")
    await make_user_market(db_session, user, market_code="BR", role="admin")

    br_pl = await make_price_list(db_session, market_code="BR", code="lojista-mut")
    eu_pl = await make_price_list(db_session, market_code="EU", code="lojista-mut")
    br_client = await make_client(
        db_session, br_pl, market_code="BR", name="MUT BR Client"
    )
    eu_client = await make_client(
        db_session, eu_pl, market_code="EU", name="MUT EU Client"
    )
    original_eu_phone = eu_client.phone
    await db_session.flush()

    br_token = create_access_token(user.id, "admin", user.auth_version, "BR")

    # ── Mutação autorizada ────────────────────────────────────────────────────
    patch_br = await client.patch(
        f"/api/v1/clients/{br_client.id}",
        json={"phone": "11999990001"},
        headers={"Authorization": f"Bearer {br_token}"},
    )
    assert patch_br.status_code == 200, patch_br.text

    # Prova de escrita: refrescar o objeto e verificar via ORM.
    await db_session.refresh(br_client)
    assert br_client.phone == "11999990001", (
        "Telefone do cliente BR não foi atualizado no banco"
    )

    # ── Mutação negada ────────────────────────────────────────────────────────
    patch_eu = await client.patch(
        f"/api/v1/clients/{eu_client.id}",
        json={"phone": "000000000"},
        headers={"Authorization": f"Bearer {br_token}"},
    )
    assert patch_eu.status_code == 404, patch_eu.text

    # Ausência de resíduo: cliente EU inalterado (bypassa filtro de mercado).
    eu_after = (await db_session.execute(
        select(Client)
        .where(Client.id == eu_client.id)
        .execution_options(skip_market_scope=True)
    )).scalar_one_or_none()
    assert eu_after is not None, "Cliente EU não deve ser excluído"
    assert eu_after.phone == original_eu_phone, (
        f"Cliente EU foi alterado pela mutação negada: "
        f"esperado={original_eu_phone!r} actual={eu_after.phone!r}"
    )
