"""Ficha de cliente de Portugal: editar um cliente existente precisa gravar.

Reproduz o que a tela de edição envia (PATCH com a ficha inteira) contra
PostgreSQL real e confere, campo a campo, o que ficou gravado. Cobre também o
VAT/Tax ID único, o fim do número de morada e o "cliente contactado" da ficha EU.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.market import PriceList
from tests.factories import (
    make_client,
    make_price_list,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _ficha_editada(**extra) -> dict:
    """Payload equivalente ao que o formulário de edição EU manda."""
    return {
        "name": "Casa Atlântico Lda",
        "contact_name": "Maria Silva",
        "client_type": "arquiteto",
        "observation": "Ligar depois das 14h.",
        "contacted": True,
        "phone": "+351 912 000 111",
        "email": "casa@atlantico.example",
        "cpf_cnpj": None,
        "tax_id": "PT501964843",
        "country": "Portugal",
        "region": "Lisboa",
        "cep": "1250-096",
        "address": "Rua das Flores 10",
        "city": "Lisboa",
        "state": "--",
        "price_profile": "corporativo",
        **extra,
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _eu_admin(db: AsyncSession, email: str):
    user = await make_user(db, email=email)
    await make_user_market(db, user, market_code="EU", role="admin")
    return create_access_token(user.id, "admin", user.auth_version, "EU")


async def _cliente_eu(db: AsyncSession, name: str = "Casa Atlântico", **kwargs):
    # As tabelas de preço EU já vêm das migrations; o teste usa as reais.
    lojista = (await db.execute(
        select(PriceList).where(PriceList.market_code == "EU", PriceList.code == "lojista")
    )).scalar_one()
    client = await make_client(db, lojista, market_code="EU", name=name, **kwargs)
    await db.flush()
    return client


async def _representante(db: AsyncSession, email: str):
    rep = await make_representative(db, market_code="EU", name="Rep PT")
    user = await make_user(db, email=email)
    await make_user_market(db, user, market_code="EU", role="representante", rep_id=rep.id)
    token = create_access_token(user.id, "representante", user.auth_version, "EU")
    return rep, token


def _assert_gravado(cliente, esperado: dict) -> None:
    for campo, valor in esperado.items():
        assert getattr(cliente, campo) == valor, f"{campo} não foi gravado"


# ── Editar grava ─────────────────────────────────────────────────────────────

async def test_admin_edita_ficha_eu_e_tudo_fica_gravado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _eu_admin(db_session, "ficha-admin@ilya-test.invalid")
    cliente = await _cliente_eu(db_session)

    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}", json=_ficha_editada(), headers=_auth(token)
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["contacted"] is True

    await db_session.refresh(cliente)
    _assert_gravado(cliente, _ficha_editada())


async def test_representante_edita_ficha_eu_inclusive_o_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Antes o VAT/Tax ID do representante era descartado com 200."""
    rep, token = await _representante(db_session, "ficha-rep@ilya-test.invalid")
    cliente = await _cliente_eu(db_session)
    cliente.rep_id = rep.id
    await db_session.flush()

    # O e-mail do representante continua restrito: a ficha reenvia o valor
    # gravado (nenhum), então nada é recusado.
    ficha = _ficha_editada(email=None)
    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}", json=ficha, headers=_auth(token)
    )
    assert resposta.status_code == 200, resposta.text

    await db_session.refresh(cliente)
    _assert_gravado(cliente, ficha)


async def test_representante_nao_perde_em_silencio_a_troca_de_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    rep, token = await _representante(db_session, "ficha-rep-mail@ilya-test.invalid")
    cliente = await _cliente_eu(db_session)
    cliente.rep_id = rep.id
    await db_session.flush()

    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}",
        json={"phone": "+351 900 000 000", "email": "novo@exemplo.example"},
        headers=_auth(token),
    )
    assert resposta.status_code == 403
    assert "e-mail" in resposta.json()["detail"]

    await db_session.refresh(cliente)
    assert cliente.email is None
    assert cliente.phone != "+351 900 000 000", "nada deve ser gravado quando a edição é recusada"


# ── VAT / Tax ID único ───────────────────────────────────────────────────────

async def test_vat_repetido_na_criacao_devolve_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _eu_admin(db_session, "vat-criar@ilya-test.invalid")
    existente = await _cliente_eu(db_session, name="Já existe")
    existente.tax_id = "PT 501.964-843"
    await db_session.flush()

    novo = {
        "name": "Outro Cliente", "phone": "+351 910 000 000", "cep": "1000-001",
        "address": "Rua Dois", "city": "Porto", "state": "--", "country": "Portugal",
        "tax_id": "pt501964843",
    }
    resposta = await client.post("/api/v1/clients", json=novo, headers=_auth(token))
    assert resposta.status_code == 409, resposta.text
    assert "VAT" in resposta.json()["detail"]

    ok = await client.post(
        "/api/v1/clients", json={**novo, "tax_id": "PT999888777"}, headers=_auth(token)
    )
    assert ok.status_code == 201, ok.text


async def test_vat_repetido_na_edicao_devolve_409_mas_o_proprio_cliente_pode_reenviar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _eu_admin(db_session, "vat-editar@ilya-test.invalid")
    primeiro = await _cliente_eu(db_session, name="Primeiro")
    primeiro.tax_id = "PT501964843"
    segundo = await _cliente_eu(db_session, name="Segundo")
    await db_session.flush()

    colisao = await client.patch(
        f"/api/v1/clients/{segundo.id}", json={"tax_id": " pt-501 964.843 "}, headers=_auth(token)
    )
    assert colisao.status_code == 409, colisao.text

    # O dono do VAT reenviando o mesmo número (outra grafia) não colide consigo.
    proprio = await client.patch(
        f"/api/v1/clients/{primeiro.id}",
        json={"tax_id": "PT 501 964 843", "phone": "+351 911 111 111"},
        headers=_auth(token),
    )
    assert proprio.status_code == 200, proprio.text


async def test_vat_igual_em_outro_mercado_nao_colide(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _eu_admin(db_session, "vat-mercado@ilya-test.invalid")
    br_pl = await make_price_list(db_session, market_code="BR", code="lojista-vat")
    br_cliente = await make_client(db_session, br_pl, market_code="BR", name="Cliente BR")
    br_cliente.tax_id = "PT501964843"
    cliente = await _cliente_eu(db_session)
    await db_session.flush()

    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}", json={"tax_id": "PT501964843"}, headers=_auth(token)
    )
    assert resposta.status_code == 200, resposta.text


async def test_ficha_com_vat_duplicado_antigo_continua_editavel_nos_outros_campos(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Duplicados que já existem em produção não podem travar a edição."""
    token = await _eu_admin(db_session, "vat-legado@ilya-test.invalid")
    a = await _cliente_eu(db_session, name="Legado A")
    b = await _cliente_eu(db_session, name="Legado B")
    a.tax_id = b.tax_id = "PT501964843"
    await db_session.flush()

    resposta = await client.patch(
        f"/api/v1/clients/{a.id}",
        json={"tax_id": "PT501964843", "phone": "+351 922 222 222"},
        headers=_auth(token),
    )
    assert resposta.status_code == 200, resposta.text


# ── Número de morada e "contactado" ──────────────────────────────────────────

async def test_ficha_eu_ignora_numero_e_grava_contactado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _eu_admin(db_session, "ficha-numero@ilya-test.invalid")

    criado = await client.post(
        "/api/v1/clients",
        json={
            "name": "Sem Número", "phone": "+351 910 000 001", "cep": "1000-001",
            "address": "Rua Três", "city": "Lisboa", "state": "--", "country": "Portugal",
            "numero": "12A", "contacted": True,
        },
        headers=_auth(token),
    )
    assert criado.status_code == 201, criado.text
    assert criado.json()["numero"] is None
    assert criado.json()["contacted"] is True

    id_ = criado.json()["id"]
    editado = await client.patch(
        f"/api/v1/clients/{id_}", json={"contacted": False, "numero": "99"}, headers=_auth(token)
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["contacted"] is False
    assert editado.json()["numero"] is None

    # contacted nulo não derruba a coluna NOT NULL nem apaga o valor.
    nulo = await client.patch(f"/api/v1/clients/{id_}", json={"contacted": None}, headers=_auth(token))
    assert nulo.status_code == 200, nulo.text
    assert nulo.json()["contacted"] is False
