import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.deps import get_market_principal, get_platform_principal, require_platform_capability
from app.api.routers.auth import _rotate_refresh_token, login, platform_login, switch_market
from app.api.routers.markets import VatDecisionRequest, decide_europe_vat
from app.api.routers.users import (
    _build_market_links,
    _replace_market_links,
    create_user,
    update_user,
)
from app.core.markets import MARKETS, MarketPrincipal, PlatformPrincipal
from app.core.platform import lock_platform_admin_guard
from app.core.security import create_access_token, decode_access_token
from app.models.market import UserMarket
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    SwitchMarketRequest,
    UserCreate,
    UserMarketAccessInput,
    UserUpdate,
)


def _user(**overrides):
    values = {
        "id": uuid.uuid4(),
        "email": "admin@example.com",
        "username": "admin",
        "hashed_password": "hash",
        "full_name": "Admin",
        "role": UserRole.admin,
        "is_active": True,
        "must_change_password": False,
        "auth_version": 3,
        "failed_login_attempts": 0,
        "locked_until": None,
        "home_market": "BR",
    }
    values.update(overrides)
    return User(**values)


def _result(*, scalar=None, scalars=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = scalars or []
    return result


def test_market_actor_uses_the_role_and_links_of_each_market():
    user = _user()
    br = UserMarket(user_id=user.id, market_code="BR", role="admin", status="active")
    eu_rep = uuid.uuid4()
    eu = UserMarket(
        user_id=user.id,
        market_code="EU",
        role="representante",
        status="active",
        rep_id=eu_rep,
    )
    assert MarketPrincipal(user, MARKETS["BR"], br).actor.role == UserRole.admin
    eu_actor = MarketPrincipal(user, MARKETS["EU"], eu).actor
    assert eu_actor.role == UserRole.representante
    assert eu_actor.rep_id == eu_rep
    assert eu_actor.linked_id is None


def test_platform_token_has_no_market_and_commercial_dependency_rejects_it():
    async def run():
        user = _user()
        token = create_access_token(user.id, None, user.auth_version, None, scope="platform")
        payload = decode_access_token(token)
        assert payload["scope"] == "platform"
        assert "market" not in payload
        with pytest.raises(HTTPException) as exc:
            await get_market_principal(token=token, db=AsyncMock())
        assert exc.value.status_code == 401
    asyncio.run(run())


def test_market_token_is_rejected_by_platform_dependency():
    async def run():
        user = _user()
        token = create_access_token(user.id, "admin", user.auth_version, "BR")
        with pytest.raises(HTTPException) as exc:
            await get_platform_principal(token=token, db=AsyncMock())
        assert exc.value.status_code == 401
    asyncio.run(run())


def test_platform_admin_satisfies_specific_platform_capabilities():
    dependency = require_platform_capability("activate_market")
    principal = PlatformPrincipal(_user(), frozenset({"platform_admin"}))
    assert dependency(principal=principal) is principal
    with pytest.raises(HTTPException) as exc:
        dependency(principal=PlatformPrincipal(_user(), frozenset({"read_outbox"})))
    assert exc.value.status_code == 403


def test_platform_login_does_not_require_a_commercial_market():
    async def run():
        user = _user()
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [
            _result(scalar=user),
            _result(scalar=None),
            _result(),
            _result(scalar=user.id),
        ]
        response = MagicMock()
        request = SimpleNamespace(
            state=SimpleNamespace(request_id="test"),
            client=SimpleNamespace(host="203.0.113.10"),
            headers={},
        )
        with patch("app.api.routers.auth.verify_password", return_value=True):
            result = await platform_login.__wrapped__(
                request=request,
                response=response,
                payload=LoginRequest(identifier=user.email, password="secret"),
                db=db,
            )
        payload = decode_access_token(result.access_token)
        assert payload["scope"] == "platform"
        assert "market" not in payload
        stored = db.add.call_args.args[0]
        assert stored.scope == "platform"
        assert stored.active_market is None
        cookie = response.set_cookie.call_args.kwargs
        assert cookie["key"] == "ilya_platform_refresh"
        assert cookie["path"] == "/api/v1/platform/auth"
    asyncio.run(run())


def test_refresh_cookie_cannot_cross_from_market_to_platform_scope():
    async def run():
        stored = SimpleNamespace(scope="market")
        db = AsyncMock()
        db.execute.return_value = _result(scalar=stored)
        with pytest.raises(HTTPException) as exc:
            await _rotate_refresh_token(db, "market-cookie", expected_scope="platform")
        assert exc.value.status_code == 401
        db.commit.assert_not_awaited()
    asyncio.run(run())


def test_commercial_login_denies_identity_without_active_market():
    async def run():
        user = _user()
        db = AsyncMock()
        db.execute.side_effect = [
            _result(scalar=user), _result(scalar=None), _result(), _result(scalars=[])
        ]
        request = SimpleNamespace(
            state=SimpleNamespace(request_id="test"),
            client=SimpleNamespace(host="203.0.113.10"),
            headers={},
        )
        with patch("app.api.routers.auth.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                await login.__wrapped__(
                    request=request,
                    response=MagicMock(),
                    payload=LoginRequest(identifier=user.email, password="secret"),
                    db=db,
                )
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_switch_market_emits_the_target_markets_role():
    async def run():
        user = _user()
        br = UserMarket(user_id=user.id, market_code="BR", role="admin", status="active")
        eu = UserMarket(
            user_id=user.id,
            market_code="EU",
            role="representante",
            status="active",
            rep_id=uuid.uuid4(),
        )
        stored = SimpleNamespace(active_market="BR", scope="market")
        db = AsyncMock()
        db.execute.return_value = _result(scalar=stored)
        with patch("app.api.routers.auth.require_market_access", AsyncMock(return_value=eu)):
            result = await switch_market(
                body=SwitchMarketRequest(market="EU"),
                request=SimpleNamespace(),
                db=db,
                principal=MarketPrincipal(user, MARKETS["BR"], br),
                refresh_token="refresh",
                _origin_guard=None,
            )
        payload = decode_access_token(result.access_token)
        assert payload["market"] == "EU"
        assert payload["role"] == "representante"
        assert stored.active_market == "EU"
    asyncio.run(run())


def test_vat_approval_requires_permission_in_the_active_eu_market():
    async def run():
        user = _user()
        br = UserMarket(
            user_id=user.id,
            market_code="BR",
            role="admin",
            status="active",
            can_approve_tax=True,
        )
        eu_without_permission = UserMarket(
            user_id=user.id,
            market_code="EU",
            role="admin",
            status="active",
            can_approve_tax=False,
        )
        body = VatDecisionRequest(status="approved", vat_rate=23)
        for principal in (
            MarketPrincipal(user, MARKETS["BR"], br),
            MarketPrincipal(user, MARKETS["EU"], eu_without_permission),
        ):
            with pytest.raises(HTTPException) as exc:
                await decide_europe_vat(uuid.uuid4(), body, AsyncMock(), principal)
            assert exc.value.status_code == 403
    asyncio.run(run())


def test_market_link_validation_bypasses_session_scope_but_filters_market_explicitly():
    async def run():
        rep_id = uuid.uuid4()
        db = AsyncMock()
        db.execute.return_value = _result(scalar=rep_id)
        links = await _build_market_links(
            [UserMarketAccessInput(
                market_code="EU",
                role=UserRole.representante,
                status="active",
                rep_id=rep_id,
            )],
            db,
        )
        statement = db.execute.call_args.args[0]
        assert statement.get_execution_options()["skip_market_scope"] is True
        assert "representatives.market_code" in str(statement)
        assert links[0].market_code == "EU"
        assert links[0].rep_id == rep_id
    asyncio.run(run())


def test_replacing_market_links_updates_each_market_without_reinserting_primary_keys():
    async def run():
        user = _user()
        br = UserMarket(
            user_id=user.id,
            market_code="BR",
            role="admin",
            status="active",
            can_view_dashboard=True,
        )
        eu = UserMarket(
            user_id=user.id,
            market_code="EU",
            role="representante",
            status="active",
            rep_id=uuid.uuid4(),
        )
        user.allowed_market_links = [br, eu]
        new_eu_rep = uuid.uuid4()
        desired = [
            UserMarket(
                market_code="BR",
                role="admin",
                status="active",
                can_view_dashboard=False,
                can_approve_tax=False,
            ),
            UserMarket(
                market_code="EU",
                role="representante",
                status="suspended",
                rep_id=new_eu_rep,
                can_approve_tax=True,
            ),
        ]
        db = AsyncMock()
        await _replace_market_links(db, user, desired)
        db.delete.assert_not_awaited()
        assert br.role == "admin"
        assert br.can_view_dashboard is False
        assert eu.role == "representante"
        assert eu.status == "suspended"
        assert eu.rep_id == new_eu_rep
        assert eu.can_approve_tax is True
        assert user.allowed_market_links == [br, eu]
    asyncio.run(run())


def test_platform_identity_can_be_created_without_commercial_market():
    async def run():
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = _result()
        body = UserCreate(
            email="platform-only@example.com",
            full_name="Platform Operator",
            password="Strong-password-123!",
            market_accesses=[],
        )
        with patch("app.api.routers.users.hash_password", return_value="hashed"):
            created = await create_user(body=body, db=db, _=MagicMock())
        assert created.allowed_market_links == []
        assert created.allowed_markets == []
        assert created.home_market == "BR"
        assert created.role == UserRole.vendedor
        assert created.rep_id is None
        assert created.linked_id is None
        db.add.assert_called_once_with(created)
        db.commit.assert_awaited_once()
    asyncio.run(run())


def test_replacing_last_market_link_keeps_platform_identity_without_access():
    async def run():
        user = _user()
        br = UserMarket(user_id=user.id, market_code="BR", role="admin", status="active")
        user.allowed_market_links = [br]
        db = AsyncMock()
        await _replace_market_links(db, user, [])
        db.delete.assert_awaited_once_with(br)
        assert user.allowed_market_links == []
        assert user.allowed_markets == []
    asyncio.run(run())


def test_platform_admin_guard_uses_transaction_advisory_lock():
    async def run():
        db = AsyncMock()
        await lock_platform_admin_guard(db)
        statement = str(db.execute.await_args.args[0])
        assert "pg_advisory_xact_lock" in statement
    asyncio.run(run())


def test_changing_market_link_revokes_only_commercial_refresh_families():
    """Checkpoint 04: alterar vínculo comercial revoga a sessão de mercado na
    hora, sem derrubar a sessão de plataforma e sem girar `auth_version`."""
    async def run():
        user = _user()
        br = UserMarket(
            user_id=user.id,
            market_code="BR",
            role="admin",
            status="active",
            can_view_dashboard=True,
        )
        user.allowed_market_links = [br]
        version_before = user.auth_version
        db = AsyncMock()
        db.execute.return_value = _result(scalar=user)
        body = UserUpdate(
            market_accesses=[
                UserMarketAccessInput(
                    market_code="BR",
                    role=UserRole.produtos,
                    status="active",
                )
            ]
        )
        with patch(
            "app.api.routers.users._build_market_links",
            new=AsyncMock(return_value=[
                UserMarket(
                    market_code="BR",
                    role="produtos",
                    status="active",
                    can_view_dashboard=False,
                )
            ]),
        ):
            await update_user(user_id=user.id, body=body, db=db, _=MagicMock())

        revocations = [
            str(call.args[0])
            for call in db.execute.await_args_list
            if "UPDATE refresh_tokens" in str(call.args[0])
        ]
        assert len(revocations) == 1, "o vínculo comercial deve gerar uma revogação"
        assert "refresh_tokens.scope" in revocations[0], (
            "a revogação precisa ser restrita ao escopo comercial"
        )
        scope_params = [
            value
            for call in db.execute.await_args_list
            if "UPDATE refresh_tokens" in str(call.args[0])
            for value in call.args[0].compile().params.values()
        ]
        assert "market" in scope_params
        assert "platform" not in scope_params
        # O papel é relido de user_markets a cada requisição, então o access
        # token curto não precisa ser invalidado por versão.
        assert user.auth_version == version_before
        assert br.role == "produtos"
        assert br.can_view_dashboard is False
        db.commit.assert_awaited_once()
    asyncio.run(run())


def test_stale_auth_version_token_is_rejected_after_identity_change():
    """Checkpoint 04: suspender a identidade gira `auth_version`, e o access
    token emitido antes disso deixa de autenticar na requisição seguinte."""
    async def run():
        user = _user()
        token = create_access_token(user.id, "admin", user.auth_version, "BR")
        assert decode_access_token(token)["ver"] == user.auth_version

        user.auth_version += 1  # efeito de suspensão/rename em update_user
        br = UserMarket(
            user_id=user.id, market_code="BR", role="admin", status="active"
        )
        db = AsyncMock()
        db.sync_session = SimpleNamespace(info={})
        db.execute.return_value = _result(scalar=user, scalars=[br])
        with pytest.raises(HTTPException) as exc:
            await get_market_principal(token=token, db=db)
        assert exc.value.status_code == 401

        # Mesma identidade e mesmo vínculo: só a versão do token mudou.
        fresh = create_access_token(user.id, "admin", user.auth_version, "BR")
        principal = await get_market_principal(token=fresh, db=db)
        assert principal.market.code == "BR"
    asyncio.run(run())


def test_vinculo_pendente_com_papel_nulo_e_serializavel():
    """Regressão de produção, 06/10: `/auth/me` devolvia 500 logo após o login.

    A `rbac_r2a` deixa `user_markets.role` nullable e põe os vínculos legados em
    `pending` com papel nulo — por desenho, para que não concedam acesso antes
    da revisão nominal. O modelo permitia (`Mapped[str | None]`), mas
    `UserMarketAccessInput.role` era `UserRole` obrigatório, então o Pydantic
    estourava `ValidationError ... v/enum` ao serializar a conta.

    Atingia justamente quem tem vínculo nos dois mercados: os dois
    administradores globais ficaram sem conseguir usar o sistema, embora o
    `POST /auth/login` respondesse 200 — o 500 vinha no `/auth/me` seguinte.
    """
    pendente = UserMarketAccessInput(
        market_code="EU", role=None, status="pending"
    )
    assert pendente.role is None
    assert pendente.status == "pending"

    # Omitir o papel equivale a nulo: é o que `from_attributes` faz ao ler a
    # linha de `user_markets` com role NULL.
    omitido = UserMarketAccessInput(market_code="EU", status="pending")
    assert omitido.role is None

    # O caminho normal segue exigindo papel válido.
    ativo = UserMarketAccessInput(
        market_code="BR", role=UserRole.admin, status="active"
    )
    assert ativo.role is UserRole.admin


def test_build_market_links_recusa_papel_nulo():
    """A contraparte do fix acima: nulo é legítimo na leitura, não na escrita.

    Tornar `role` nullable no schema reabriu `_build_market_links`, que faz
    `item.role.value` — com nulo seria `AttributeError`, ou seja 500 no lugar do
    422 que o schema obrigatório dava antes. Um vínculo criado por admin sem
    papel não teria leitura possível, então o caminho de escrita recusa.
    """
    async def run():
        db = MagicMock()
        with pytest.raises(HTTPException) as erro:
            await _build_market_links(
                [UserMarketAccessInput(
                    market_code="BR", role=None, status="active"
                )],
                db,
            )
        assert erro.value.status_code == 422
        assert "papel" in erro.value.detail.lower()
    asyncio.run(run())
