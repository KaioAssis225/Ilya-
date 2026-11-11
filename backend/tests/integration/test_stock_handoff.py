"""Login único com o Estoque Brasil — PR B, emissor `POST /api/v1/stock/handoff`.

Par ES256 gerado em tempo de execução (fixture `stock_keys`); nenhuma chave em
arquivo. PostgreSQL real, transação revertida por teste.
"""
import json

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.core.stock_handoff import _normalize_origin
from app.models.privacy_event import PrivacyEvent
from app.models.user import User, UserRole
from tests.factories import (
    make_client,
    make_platform_permission,
    make_price_list,
    make_user,
    make_user_market,
)
from tests.factories.stock_keys import make_es256_pair

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_URL = "/api/v1/stock/handoff"
_CLAIMS = {"iss", "aud", "typ", "sub", "ver", "iat", "exp", "jti"}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _member(
    db: AsyncSession,
    email: str,
    *,
    role: UserRole = UserRole.vendedor,
    markets: tuple[str, ...] = ("BR",),
    status: str = "active",
    flag: bool = True,
) -> User:
    user = await make_user(db, email=email, role=role, home_market=markets[0])
    user.has_stock_access = flag
    for code in markets:
        linked = None
        if role == UserRole.cliente:
            prices = await make_price_list(db, market_code=code)
            linked = (await make_client(db, prices, market_code=code)).id
        await make_user_market(
            db, user, market_code=code, role=role.value, status=status,
            linked_client_id=linked,
        )
    await db.flush()
    await db.refresh(user, ["allowed_market_links"])
    return user


def _market_token(user: User, market: str = "BR") -> dict[str, str]:
    return _bearer(create_access_token(user.id, user.role.value, user.auth_version, market))


async def _audit(db: AsyncSession, user: User, action: str) -> list[PrivacyEvent]:
    return list((await db.execute(select(PrivacyEvent).where(
        PrivacyEvent.subject_id == user.id, PrivacyEvent.action == action,
    ))).scalars().all())


def _decode(token: str, public_pem: str) -> dict:
    return jwt.decode(
        token, public_pem, algorithms=["ES256"], audience="ilya-estoque", issuer="ilya"
    )


# ── Token ────────────────────────────────────────────────────────────────────

async def test_emite_token_es256_com_todos_os_claims_e_nada_alem(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-ok@ilya-test.invalid")
    response = await client.post(_URL, headers=_market_token(user))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in"] == 60
    assert response.headers["cache-control"] == "no-store"

    header = jwt.get_unverified_header(body["assertion"])
    assert header == {"alg": "ES256", "typ": "JWT", "kid": "stock-handoff-test"}

    claims = _decode(body["assertion"], stock_keys)  # confere assinatura, iss e aud
    assert set(claims) == _CLAIMS
    assert claims["typ"] == "stock-handoff"
    assert claims["sub"] == str(user.id)
    assert claims["ver"] == user.auth_version
    assert claims["exp"] - claims["iat"] == 60


async def test_token_nao_carrega_dado_pessoal(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-pii@ilya-test.invalid", role=UserRole.admin)
    user.full_name = "Fulano de Tal"
    await db_session.flush()
    token = (await client.post(_URL, headers=_market_token(user))).json()["assertion"]
    payload = jwt.decode(token, options={"verify_signature": False})
    raw = json.dumps(payload)
    for forbidden in ("hf-pii", "Fulano", "admin", "email", "role", "name", "phone"):
        assert forbidden not in raw


async def test_jti_muda_a_cada_chamada(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-jti@ilya-test.invalid")
    first = (await client.post(_URL, headers=_market_token(user))).json()["assertion"]
    second = (await client.post(_URL, headers=_market_token(user))).json()["assertion"]
    assert _decode(first, stock_keys)["jti"] != _decode(second, stock_keys)["jti"]


async def test_assinatura_so_confere_com_a_chave_publica_do_par(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-sig@ilya-test.invalid")
    token = (await client.post(_URL, headers=_market_token(user))).json()["assertion"]
    _, other_public = make_es256_pair()
    with pytest.raises(jwt.InvalidSignatureError):
        _decode(token, other_public)
    with pytest.raises(jwt.InvalidAlgorithmError):
        jwt.decode(token, stock_keys, algorithms=["HS256"])


async def test_sessao_de_plataforma_tambem_emite(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-plat@ilya-test.invalid", role=UserRole.admin)
    await make_platform_permission(db_session, user)
    token = create_access_token(user.id, None, user.auth_version, None, scope="platform")
    response = await client.post(_URL, headers=_bearer(token))
    assert response.status_code == 200, response.text


async def test_quem_tem_br_emite_mesmo_de_sessao_eu(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-eu@ilya-test.invalid", markets=("BR", "EU"))
    response = await client.post(_URL, headers=_market_token(user, "EU"))
    assert response.status_code == 200, response.text


# ── Auditoria ────────────────────────────────────────────────────────────────

async def test_auditoria_registra_quem_e_quando_sem_gravar_o_token(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-aud@ilya-test.invalid")
    token = (await client.post(_URL, headers=_market_token(user))).json()["assertion"]
    [event] = await _audit(db_session, user, "stock_handoff_issued")
    assert event.actor_user_id == user.id and event.created_at is not None
    assert set(event.context) <= {"market", "kid", "jti"}
    assert token not in json.dumps(event.context)
    assert event.context["jti"] == _decode(token, stock_keys)["jti"]


# ── Recusas (403 genérico, motivo só na auditoria) ───────────────────────────

async def _expect_forbidden(client, db, user, reason, headers=None):
    response = await client.post(_URL, headers=headers or _market_token(user))
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "Acesso ao Estoque não autorizado."}
    [event] = await _audit(db, user, "stock_handoff_denied")
    assert event.context["reason"] == reason


async def test_sem_flag_e_recusado(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-noflag@ilya-test.invalid", flag=False)
    await _expect_forbidden(client, db_session, user, "no_stock_access")


async def test_flag_marcada_mas_sem_br_e_recusada(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-eu-only@ilya-test.invalid", markets=("EU",))
    await _expect_forbidden(client, db_session, user, "no_br_market", _market_token(user, "EU"))


async def test_vinculo_br_pendente_e_recusado(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-pend@ilya-test.invalid", status="pending")
    token = create_access_token(user.id, None, user.auth_version, None, scope="platform")
    await make_platform_permission(db_session, user)
    await _expect_forbidden(client, db_session, user, "no_br_market", _bearer(token))


async def test_cliente_e_recusado(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-cli@ilya-test.invalid", role=UserRole.cliente)
    await _expect_forbidden(client, db_session, user, "role_blocked")


async def test_benchmark_readonly_e_recusado(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-bench@ilya-test.invalid", role=UserRole.benchmark_readonly)
    response = await client.post(_URL, headers=_market_token(user))
    assert response.status_code == 403, response.text  # canário: somente leitura
    assert await _audit(db_session, user, "stock_handoff_issued") == []


async def test_troca_de_senha_pendente_e_recusada(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-mcp@ilya-test.invalid")
    user.must_change_password = True
    await db_session.flush()
    await _expect_forbidden(client, db_session, user, "must_change_password")


async def test_usuario_inativo_e_rejeitado_com_401(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-off@ilya-test.invalid")
    headers = _market_token(user)
    user.is_active = False
    await db_session.flush()
    assert (await client.post(_URL, headers=headers)).status_code == 401


async def test_sem_bearer_e_auth_version_velho_dao_401(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-401@ilya-test.invalid")
    assert (await client.post(_URL)).status_code == 401
    headers = _market_token(user)
    user.auth_version += 1
    await db_session.flush()
    assert (await client.post(_URL, headers=headers)).status_code == 401


# ── Chave ausente / inválida ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("STOCK_HANDOFF_PRIVATE_KEY", ""),
        ("STOCK_HANDOFF_PRIVATE_KEY", "isto-nao-e-um-pem"),
        ("STOCK_HANDOFF_KID", ""),
        ("STOCK_APP_ORIGIN", ""),
        ("STOCK_APP_ORIGIN", "http://estoque.example.com"),  # http fora de localhost
        ("STOCK_APP_ORIGIN", "https://estoque.example.com/entrar"),  # com caminho
    ],
)
async def test_sem_configuracao_valida_responde_503_e_o_link_some(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str,
    monkeypatch: pytest.MonkeyPatch, field: str, value: str,
) -> None:
    monkeypatch.setattr(settings, field, value)
    user = await _member(db_session, "hf-503@ilya-test.invalid")
    headers = _market_token(user)
    response = await client.post(_URL, headers=headers)
    assert response.status_code == 503, response.text
    assert "isto-nao-e-um-pem" not in response.text
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["can_access_stock"] is False
    assert (await client.get("/api/v1/stock/link", headers=headers)).status_code == 503


async def test_chave_de_outra_curva_nao_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.core.stock_handoff import get_signer

    wrong = ec.generate_private_key(ec.SECP384R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(settings, "STOCK_HANDOFF_PRIVATE_KEY", wrong)
    monkeypatch.setattr(settings, "STOCK_HANDOFF_KID", "k")
    monkeypatch.setattr(settings, "STOCK_APP_ORIGIN", "https://estoque.example.com")
    assert get_signer() is None


async def test_normalizacao_da_origem() -> None:
    assert _normalize_origin("https://ilya-estoque.vercel.app") == "https://ilya-estoque.vercel.app"
    assert _normalize_origin("https://ilya-estoque.vercel.app/") == "https://ilya-estoque.vercel.app"
    assert _normalize_origin("http://localhost:5174") == "http://localhost:5174"
    assert _normalize_origin("http://ilya-estoque.vercel.app") is None
    assert _normalize_origin("https://x.app/caminho") is None
    assert _normalize_origin("javascript:alert(1)") is None
    assert _normalize_origin("") is None


# ── Rate limit e /stock/link ─────────────────────────────────────────────────

async def test_limite_de_taxa_por_usuario(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    user = await _member(db_session, "hf-rate@ilya-test.invalid")
    other = await _member(db_session, "hf-rate2@ilya-test.invalid")
    headers = _market_token(user)
    statuses = [(await client.post(_URL, headers=headers)).status_code for _ in range(11)]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
    # O balde é por usuário: o colega não é afetado.
    assert (await client.post(_URL, headers=_market_token(other))).status_code == 200


async def test_link_devolve_a_origem_so_para_quem_pode(
    client: AsyncClient, db_session: AsyncSession, stock_keys: str
) -> None:
    ok = await _member(db_session, "hf-link@ilya-test.invalid")
    no = await _member(db_session, "hf-link2@ilya-test.invalid", flag=False)
    allowed = await client.get("/api/v1/stock/link", headers=_market_token(ok))
    assert allowed.status_code == 200
    assert allowed.json() == {"origin": "http://localhost:5174"}
    assert (await client.get("/api/v1/stock/link", headers=_market_token(no))).status_code == 403
    assert (await client.get("/api/v1/stock/link")).status_code == 401
