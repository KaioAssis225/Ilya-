"""Contatos adicionais do cliente e edição completa pelo representante dono.

PostgreSQL real. Cobre: lista de contatos na criação/edição/leitura (BR e EU),
validação por linha, ownership, exclusão/anonimização e a permissão do
representante sobre e-mail, CPF/CNPJ e VAT dos clientes que ele criou.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.client_contact import ClientContact
from app.models.market import PriceList
from tests.factories import (
    make_client,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _novo_cliente(**extra) -> dict:
    return {
        "name": "Casa Atlântico", "phone": "+351 910 000 000", "cep": "1000-001",
        "address": "Rua Um", "city": "Lisboa", "state": "--", "country": "Portugal",
        **extra,
    }


async def _admin(db: AsyncSession, market: str, email: str) -> str:
    user = await make_user(db, email=email)
    await make_user_market(db, user, market_code=market, role="admin")
    return create_access_token(user.id, "admin", user.auth_version, market)


async def _rep(db: AsyncSession, email: str, market: str = "EU"):
    rep = await make_representative(db, market_code=market, name=f"Rep {email}")
    user = await make_user(db, email=email)
    await make_user_market(db, user, market_code=market, role="representante", rep_id=rep.id)
    return rep, user, create_access_token(user.id, "representante", user.auth_version, market)


async def _lojista(db: AsyncSession, market: str) -> PriceList:
    return (await db.execute(
        select(PriceList).where(PriceList.market_code == market, PriceList.code == "lojista")
    )).scalar_one()


# ── Contatos adicionais ──────────────────────────────────────────────────────

async def test_contatos_na_criacao_leitura_e_edicao_eu(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin(db_session, "EU", "contatos-eu@ilya-test.invalid")
    contatos = [
        {"name": "Maria Silva", "phone": "+351 911 111 111", "email": "maria@exemplo.example"},
        {"name": "João Costa", "phone": "", "email": ""},
    ]
    criado = await client.post(
        "/api/v1/clients", json=_novo_cliente(contacts=contatos), headers=_auth(token)
    )
    assert criado.status_code == 201, criado.text
    lido = criado.json()["contacts"]
    assert [c["name"] for c in lido] == ["Maria Silva", "João Costa"]
    assert lido[0]["email"] == "maria@exemplo.example"
    assert lido[1]["phone"] is None and lido[1]["email"] is None

    id_ = criado.json()["id"]
    get = await client.get(f"/api/v1/clients/{id_}", headers=_auth(token))
    assert [c["name"] for c in get.json()["contacts"]] == ["Maria Silva", "João Costa"]
    listagem = await client.get("/api/v1/clients", headers=_auth(token))
    assert [c["name"] for c in listagem.json()[0]["contacts"]] == ["Maria Silva", "João Costa"]

    # Sem `contacts` no PATCH, a lista não muda.
    sem = await client.patch(f"/api/v1/clients/{id_}", json={"city": "Porto"}, headers=_auth(token))
    assert sem.status_code == 200 and len(sem.json()["contacts"]) == 2

    # A lista enviada substitui a atual, na ordem enviada.
    troca = await client.patch(
        f"/api/v1/clients/{id_}",
        json={"contacts": [{"name": "Ana Reis", "phone": "+351 922 222 222"}, {"name": "Rui Dias"}]},
        headers=_auth(token),
    )
    assert troca.status_code == 200, troca.text
    assert [c["name"] for c in troca.json()["contacts"]] == ["Ana Reis", "Rui Dias"]
    total = (await db_session.execute(
        select(func.count()).select_from(ClientContact).where(ClientContact.client_id == id_)
    )).scalar_one()
    assert total == 2, "os contatos antigos devem ser removidos, não acumulados"

    # Lista vazia limpa todos.
    limpa = await client.patch(f"/api/v1/clients/{id_}", json={"contacts": []}, headers=_auth(token))
    assert limpa.status_code == 200 and limpa.json()["contacts"] == []


async def test_contatos_tambem_valem_no_brasil(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin(db_session, "BR", "contatos-br@ilya-test.invalid")
    cliente = await make_client(db_session, await _lojista(db_session, "BR"), market_code="BR", name="Cliente BR")
    await db_session.flush()

    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}",
        json={"contacts": [{"name": "Carlos", "phone": "(11) 90000-0000", "email": "c@exemplo.example"}]},
        headers=_auth(token),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["contacts"][0]["name"] == "Carlos"


@pytest.mark.parametrize(
    "contato",
    [
        {"name": "   "},
        {"name": ""},
        {"phone": "+351 911 111 111"},
        {"name": "Fulano", "email": "isto-nao-e-email"},
        {"name": "Fulano", "phone": "1" * 21},
    ],
)
async def test_contato_invalido_recusa_422(
    contato: dict, client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin(db_session, "EU", "contato-invalido@ilya-test.invalid")
    resposta = await client.post(
        "/api/v1/clients", json=_novo_cliente(contacts=[contato]), headers=_auth(token)
    )
    assert resposta.status_code == 422, resposta.text


async def test_contatos_apagados_com_o_cliente_e_na_anonimizacao(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _admin(db_session, "EU", "contatos-lgpd@ilya-test.invalid")
    contatos = [{"name": "Maria", "email": "maria@exemplo.example"}]

    a = (await client.post("/api/v1/clients", json=_novo_cliente(contacts=contatos), headers=_auth(token))).json()
    anon = await client.post(f"/api/v1/clients/{a['id']}/anonymize", headers=_auth(token))
    assert anon.status_code == 204, anon.text
    depois = (await client.get(f"/api/v1/clients/{a['id']}", headers=_auth(token))).json()
    assert depois["contacts"] == []
    restantes = (await db_session.execute(
        select(func.count()).select_from(ClientContact).where(ClientContact.client_id == a["id"])
    )).scalar_one()
    assert restantes == 0

    b = (await client.post(
        "/api/v1/clients", json=_novo_cliente(name="Outro", contacts=contatos), headers=_auth(token)
    )).json()
    apagado = await client.delete(f"/api/v1/clients/{b['id']}", headers=_auth(token))
    assert apagado.status_code == 204, apagado.text
    restantes = (await db_session.execute(
        select(func.count()).select_from(ClientContact).where(ClientContact.client_id == b["id"])
    )).scalar_one()
    assert restantes == 0


async def test_representante_nao_mexe_nos_contatos_de_cliente_alheio(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, token = await _rep(db_session, "contatos-rep@ilya-test.invalid")
    outro = await make_representative(db_session, market_code="EU", name="Outro Rep")
    cliente = await make_client(db_session, await _lojista(db_session, "EU"), market_code="EU", name="Alheio")
    cliente.rep_id = outro.id
    await db_session.flush()

    resposta = await client.patch(
        f"/api/v1/clients/{cliente.id}", json={"contacts": [{"name": "Intruso"}]}, headers=_auth(token)
    )
    assert resposta.status_code == 403


# ── Representante edita tudo do cliente que ele criou ────────────────────────

async def test_representante_edita_email_e_documento_do_cliente_que_criou(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, token = await _rep(db_session, "dono@ilya-test.invalid")
    criado = await client.post(
        "/api/v1/clients", json=_novo_cliente(email="antigo@exemplo.example", tax_id="PT111111111"),
        headers=_auth(token),
    )
    assert criado.status_code == 201, criado.text

    editado = await client.patch(
        f"/api/v1/clients/{criado.json()['id']}",
        json={"email": "novo@exemplo.example", "tax_id": "PT222222222", "name": "Casa Nova"},
        headers=_auth(token),
    )
    assert editado.status_code == 200, editado.text
    corpo = editado.json()
    assert (corpo["email"], corpo["tax_id"], corpo["name"]) == (
        "novo@exemplo.example", "PT222222222", "Casa Nova",
    )


async def test_representante_nao_edita_email_de_cliente_da_carteira_criado_por_outro(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Carteira dele, mas criado pelo admin: a regra mais restrita vale."""
    rep, _, token = await _rep(db_session, "carteira@ilya-test.invalid")
    admin_token = await _admin(db_session, "EU", "criador-admin@ilya-test.invalid")
    criado = await client.post(
        "/api/v1/clients", json=_novo_cliente(rep_id=str(rep.id), email="admin@exemplo.example"),
        headers=_auth(admin_token),
    )
    assert criado.status_code == 201, criado.text

    resposta = await client.patch(
        f"/api/v1/clients/{criado.json()['id']}",
        json={"email": "rep@exemplo.example", "phone": "+351 933 333 333"},
        headers=_auth(token),
    )
    assert resposta.status_code == 403
    assert "e-mail" in resposta.json()["detail"]


async def test_representante_nao_mexe_em_termos_comerciais_do_proprio_cliente(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, token = await _rep(db_session, "termos@ilya-test.invalid")
    criado = (await client.post("/api/v1/clients", json=_novo_cliente(), headers=_auth(token))).json()

    resposta = await client.patch(
        f"/api/v1/clients/{criado['id']}", json={"max_discount": "50.00", "email": "x@exemplo.example"},
        headers=_auth(token),
    )
    assert resposta.status_code == 200, resposta.text
    assert float(resposta.json()["max_discount"]) == 0
    assert resposta.json()["email"] == "x@exemplo.example"
