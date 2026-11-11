"""Login único com o Estoque Brasil — lado do Ilya, PR A (coluna + administração).

Regras do usuário cobertas aqui (PostgreSQL real, transação revertida por teste):
- `has_stock_access` nasce falso; só administrador da plataforma altera;
- só vale para quem tem vínculo ativo no mercado BR (EU-só é recusado);
- `cliente` e `benchmark_readonly` nunca recebem (422);
- mudar o campo incrementa `auth_version` e é auditado;
- a coluna não vaza para quem não é administrador (`/auth/me` só diz
  `can_access_stock`, calculado, e só na sessão BR);
- revogação (I-6): logout-all, troca de senha, reset administrativo e PATCH
  derrubam o access token via `auth_version`.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.stock_access import stock_access_denial
from app.models.privacy_event import PrivacyEvent
from app.models.user import User, UserRole
from tests.factories import (
    make_client,
    make_platform_permission,
    make_price_list,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PASSWORD = "TestPassword1"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _platform_headers(db: AsyncSession, capability: str = "platform_admin") -> dict[str, str]:
    admin = await make_user(
        db, email=f"plat-{capability}@ilya-test.invalid", role=UserRole.vendedor
    )
    await make_platform_permission(db, admin, capability=capability)
    return _bearer(create_access_token(admin.id, None, admin.auth_version, None, scope="platform"))


async def _member(
    db: AsyncSession,
    email: str,
    role: UserRole = UserRole.vendedor,
    markets: tuple[str, ...] = ("BR",),
    status: str = "active",
) -> User:
    user = await make_user(db, email=email, role=role, home_market=markets[0])
    for code in markets:
        linked = None
        if role == UserRole.cliente:  # vínculo de cliente exige o cadastro (CHECK)
            prices = await make_price_list(db, market_code=code)
            linked = (await make_client(db, prices, market_code=code)).id
        await make_user_market(
            db, user, market_code=code, role=role.value, status=status,
            linked_client_id=linked,
        )
    await db.refresh(user, ["allowed_market_links"])
    return user


async def _login(db: AsyncSession, user: User, market: str = "BR") -> dict[str, str]:
    """Token comercial emitido direto: o /login tem limite por IP compartilhado
    com o resto da suíte de integração e estes testes não exercitam o login."""
    await db.refresh(user)
    return _bearer(create_access_token(user.id, user.role.value, user.auth_version, market))


async def _events(db: AsyncSession, user: User, action: str) -> list[PrivacyEvent]:
    return list((await db.execute(select(PrivacyEvent).where(
        PrivacyEvent.subject_id == user.id, PrivacyEvent.action == action,
    ))).scalars().all())


async def _set_flag(client: AsyncClient, headers: dict[str, str], user: User, value: bool):
    return await client.patch(
        f"/api/v1/users/{user.id}", json={"has_stock_access": value}, headers=headers
    )


# ── Regras de elegibilidade ──────────────────────────────────────────────────

async def test_elegibilidade_exige_br_ativo_e_papel_permitido(db_session: AsyncSession) -> None:
    br = await _member(db_session, "el-br@ilya-test.invalid")
    eu_only = await _member(db_session, "el-eu@ilya-test.invalid", markets=("EU",))
    pendente = await _member(db_session, "el-pend@ilya-test.invalid", status="pending")
    cliente = await _member(db_session, "el-cli@ilya-test.invalid", role=UserRole.cliente)
    canario = await _member(db_session, "el-can@ilya-test.invalid", role=UserRole.benchmark_readonly)

    assert stock_access_denial(br) is None
    assert stock_access_denial(eu_only) == "no_br_market"
    assert stock_access_denial(pendente) == "no_br_market"
    assert stock_access_denial(cliente) == "role_blocked"
    assert stock_access_denial(canario) == "role_blocked"


# ── Default, concessão, revogação e auditoria ────────────────────────────────

async def test_default_falso_e_lista_mostra_o_campo_so_ao_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "df-alvo@ilya-test.invalid")
    headers = await _platform_headers(db_session)

    listing = await client.get("/api/v1/users", params={"q": "df-alvo"}, headers=headers)
    assert listing.status_code == 200, listing.text
    row = listing.json()[0]
    assert row["has_stock_access"] is False
    assert "can_access_stock" not in row
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False


async def test_admin_concede_e_retira_incrementando_auth_version_e_auditando(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "gr-alvo@ilya-test.invalid")
    headers = await _platform_headers(db_session)
    versao = alvo.auth_version

    granted = await _set_flag(client, headers, alvo, True)
    assert granted.status_code == 200, granted.text
    assert granted.json()["has_stock_access"] is True
    assert "can_access_stock" not in granted.json()
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is True
    assert alvo.auth_version == versao + 1
    assert len(await _events(db_session, alvo, "stock_access_granted")) == 1

    # Reenviar o mesmo valor (o formulário manda a ficha inteira) não muda nada.
    again = await _set_flag(client, headers, alvo, True)
    assert again.status_code == 200
    await db_session.refresh(alvo)
    assert alvo.auth_version == versao + 1
    assert len(await _events(db_session, alvo, "stock_access_granted")) == 1

    revoked = await _set_flag(client, headers, alvo, False)
    assert revoked.status_code == 200, revoked.text
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False
    assert alvo.auth_version == versao + 2
    assert len(await _events(db_session, alvo, "stock_access_revoked")) == 1


async def test_auditoria_nao_grava_dado_pessoal_nem_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "au-alvo@ilya-test.invalid")
    headers = await _platform_headers(db_session)
    await _set_flag(client, headers, alvo, True)
    [event] = await _events(db_session, alvo, "stock_access_granted")
    blob = repr((event.context, event.legal_basis, event.subject_type))
    assert "au-alvo@" not in blob
    assert set(event.context) <= {"market", "reason"}


async def test_criar_usuario_br_com_acesso_e_default_falso(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _platform_headers(db_session)
    base = {
        "password": "SenhaForte123", "full_name": "Novo", "role": "vendedor",
        "home_market": "BR",
        "market_accesses": [{"market_code": "BR", "role": "vendedor", "status": "active"}],
    }
    plain = await client.post(
        "/api/v1/users", json={**base, "email": "cr-plain@example.com"}, headers=headers
    )
    assert plain.status_code == 201, plain.text
    assert plain.json()["has_stock_access"] is False

    with_access = await client.post(
        "/api/v1/users",
        json={**base, "email": "cr-acesso@example.com", "has_stock_access": True},
        headers=headers,
    )
    assert with_access.status_code == 201, with_access.text
    assert with_access.json()["has_stock_access"] is True
    created = (await db_session.execute(
        select(User).where(User.email == "cr-acesso@example.com")
    )).scalar_one()
    assert created.auth_version == 1
    assert len(await _events(db_session, created, "stock_access_granted")) == 1


async def test_criar_usuario_so_eu_com_acesso_e_recusado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _platform_headers(db_session)
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "cr-eu@example.com", "password": "SenhaForte123",
            "full_name": "So EU", "role": "vendedor", "home_market": "EU",
            "market_accesses": [{"market_code": "EU", "role": "vendedor", "status": "active"}],
            "has_stock_access": True,
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    exists = (await db_session.execute(
        select(User.id).where(User.email == "cr-eu@example.com")
    )).scalar_one_or_none()
    assert exists is None


# ── Só Brasil ────────────────────────────────────────────────────────────────

async def test_usuario_so_eu_nao_recebe_o_acesso(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "eu-alvo@ilya-test.invalid", markets=("EU",))
    headers = await _platform_headers(db_session)
    denied = await _set_flag(client, headers, alvo, True)
    assert denied.status_code == 422, denied.text
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False
    assert alvo.auth_version == 0


async def test_vinculo_br_pendente_nao_conta(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    pendente = await _member(db_session, "pn-alvo@ilya-test.invalid", status="pending")
    headers = await _platform_headers(db_session)
    assert (await _set_flag(client, headers, pendente, True)).status_code == 422


async def test_acesso_vale_so_na_sessao_br(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "dm-alvo@ilya-test.invalid", markets=("BR", "EU"))
    headers = await _platform_headers(db_session)
    assert (await _set_flag(client, headers, alvo, True)).status_code == 200
    await db_session.refresh(alvo)

    br = await client.get("/api/v1/auth/me", headers=_bearer(
        create_access_token(alvo.id, "vendedor", alvo.auth_version, "BR")
    ))
    eu = await client.get("/api/v1/auth/me", headers=_bearer(
        create_access_token(alvo.id, "vendedor", alvo.auth_version, "EU")
    ))
    assert br.status_code == 200 and eu.status_code == 200
    assert br.json()["can_access_stock"] is True
    assert eu.json()["can_access_stock"] is False
    for body in (br.json(), eu.json()):
        assert "has_stock_access" not in body


async def test_retirar_br_retira_o_acesso_junto(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "rm-alvo@ilya-test.invalid", markets=("BR", "EU"))
    headers = await _platform_headers(db_session)
    assert (await _set_flag(client, headers, alvo, True)).status_code == 200
    await db_session.refresh(alvo)
    versao = alvo.auth_version

    response = await client.patch(
        f"/api/v1/users/{alvo.id}",
        json={
            "home_market": "EU",
            "market_accesses": [
                {"market_code": "EU", "role": "vendedor", "status": "active"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_stock_access"] is False
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False
    assert alvo.auth_version > versao
    [event] = await _events(db_session, alvo, "stock_access_revoked")
    assert event.context["reason"] == "auto_no_br_market"


# ── Papéis bloqueados ────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [UserRole.cliente, UserRole.benchmark_readonly])
async def test_cliente_e_benchmark_nunca_recebem(
    client: AsyncClient, db_session: AsyncSession, role: UserRole
) -> None:
    alvo = await _member(db_session, f"bl-{role.value}@ilya-test.invalid", role=role)
    headers = await _platform_headers(db_session)
    denied = await _set_flag(client, headers, alvo, True)
    assert denied.status_code == 422, denied.text
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False


# ── Só administrador altera / não vaza ───────────────────────────────────────

async def test_nao_admin_nao_altera_nem_ve_o_campo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "na-alvo@ilya-test.invalid")
    vendedor = await _member(db_session, "na-vend@ilya-test.invalid")
    admin_mercado = await _member(db_session, "na-admin@ilya-test.invalid", role=UserRole.admin)
    sem_capacidade = await _platform_headers(db_session, capability="read_outbox")

    market_headers = [await _login(db_session, u) for u in (vendedor, admin_mercado)]
    for headers in market_headers:  # token comercial: nem passa pela porta da plataforma
        denied = await _set_flag(client, headers, alvo, True)
        assert denied.status_code in (401, 403), denied.text
    assert (await _set_flag(client, {}, alvo, True)).status_code == 401
    # Plataforma sem platform_admin: 403.
    assert (await _set_flag(client, sem_capacidade, alvo, True)).status_code == 403
    # Nem a lista.
    assert (await client.get("/api/v1/users", headers=market_headers[0])).status_code in (401, 403)
    await db_session.refresh(alvo)
    assert alvo.has_stock_access is False

    own = await client.get("/api/v1/auth/me", headers=market_headers[0])
    assert own.status_code == 200
    assert "has_stock_access" not in own.json()
    assert own.json()["can_access_stock"] is False


async def test_usuario_com_acesso_ve_apenas_o_booleano_calculado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alvo = await _member(db_session, "bc-alvo@ilya-test.invalid")
    headers = await _platform_headers(db_session)
    await _set_flag(client, headers, alvo, True)
    me = await client.get("/api/v1/auth/me", headers=await _login(db_session, alvo))
    assert me.json()["can_access_stock"] is True
    assert "has_stock_access" not in me.json()


# ── I-6: revogação via auth_version ──────────────────────────────────────────

async def test_logout_all_incrementa_auth_version_e_derruba_o_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _member(db_session, "rv-logout@ilya-test.invalid")
    headers = await _login(db_session, user)
    before = user.auth_version
    assert (await client.post("/api/v1/auth/logout-all", headers=headers)).status_code == 204
    await db_session.refresh(user)
    assert user.auth_version == before + 1
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_troca_de_senha_incrementa_auth_version_e_derruba_o_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _member(db_session, "rv-pass@ilya-test.invalid")
    headers = await _login(db_session, user)
    before = user.auth_version
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": _PASSWORD, "new_password": "OutraSenha123"},
        headers=headers,
    )
    assert response.status_code == 204, response.text
    await db_session.refresh(user)
    assert user.auth_version == before + 1
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_reset_administrativo_incrementa_auth_version_e_derruba_o_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _member(db_session, "rv-reset@ilya-test.invalid")
    admin = await _platform_headers(db_session)
    headers = await _login(db_session, user)
    before = user.auth_version
    response = await client.post(
        f"/api/v1/users/{user.id}/reset-password",
        json={"new_password": "SenhaNova1234"}, headers=admin,
    )
    assert response.status_code == 204, response.text
    await db_session.refresh(user)
    assert user.auth_version == before + 1
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_desativar_usuario_incrementa_auth_version_e_derruba_o_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _member(db_session, "rv-off@ilya-test.invalid")
    admin = await _platform_headers(db_session)
    headers = await _login(db_session, user)
    before = user.auth_version
    response = await client.patch(
        f"/api/v1/users/{user.id}", json={"is_active": False}, headers=admin
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert user.auth_version == before + 1
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_retirar_acesso_ao_estoque_derruba_o_access_token_antigo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _member(db_session, "rv-stock@ilya-test.invalid")
    admin = await _platform_headers(db_session)
    await _set_flag(client, admin, user, True)
    headers = await _login(db_session, user)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    await _set_flag(client, admin, user, False)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
