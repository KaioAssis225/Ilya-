"""Vínculo cliente↔representante (carteira).

Sem `rep_id` no cadastro, um cliente criado por admin/cadastros nascia órfão
e o representante levava 403 ao faturar para ele, sem conserto pela API —
armadilha real num evento onde alguém cadastra clientes pela conta central.
Reatribuir carteira, porém, é decisão comercial: representante não escolhe.
"""
import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.deps import COMMERCIAL_ROLES, _enforce_roles, sanitize_client_update_fields
from app.api.routers.clients import (
    _CREATE_CLIENT_ROLES,
    _DELETE_CLIENT_ROLES,
    _rep_guard,
    _resolved_rep_id,
)
from app.models.client import Client
from app.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientUpdate

BASE = {
    "name": "Cliente Teste",
    "phone": "(11) 90000-0000",
    "cep": "01310-100",
    "address": "Av Paulista",
    "city": "Sao Paulo",
    "state": "SP",
}


def _user(role: UserRole, **kw):
    return User(id=uuid.uuid4(), email="x@y.com", hashed_password="h",
                full_name="Fulano", role=role, **kw)


def test_cadastro_aceita_carteira():
    rep = uuid.uuid4()
    assert ClientCreate(**BASE, rep_id=rep).rep_id == rep


def test_cadastro_sem_carteira_continua_valido():
    assert ClientCreate(**BASE).rep_id is None


def test_representante_pode_apagar_cliente():
    assert UserRole.representante in _DELETE_CLIENT_ROLES
    assert UserRole.admin in _DELETE_CLIENT_ROLES


@pytest.mark.parametrize(
    "role", [UserRole.cadastros, UserRole.produtos, UserRole.vendedor, UserRole.cliente]
)
def test_apagar_cliente_segue_fora_do_alcance_dos_demais(role):
    # A expansao foi so para o representante consertar o proprio cadastro;
    # ninguem mais ganhou exclusao de cadastro.
    assert role not in _DELETE_CLIENT_ROLES


def test_representante_so_apaga_cliente_da_propria_carteira():
    carteira = uuid.uuid4()
    rep = _user(UserRole.representante, rep_id=carteira)
    _rep_guard(Client(id=uuid.uuid4(), rep_id=carteira), rep)  # nao levanta

    with pytest.raises(HTTPException) as alheio:
        _rep_guard(Client(id=uuid.uuid4(), rep_id=uuid.uuid4()), rep)
    assert alheio.value.status_code == 403

    # Cliente orfao tambem nao: sem carteira definida ninguem e o dono.
    with pytest.raises(HTTPException) as orfao:
        _rep_guard(Client(id=uuid.uuid4(), rep_id=None), rep)
    assert orfao.value.status_code == 403


def test_edicao_aceita_carteira():
    rep = uuid.uuid4()
    assert ClientUpdate(rep_id=rep).rep_id == rep


@pytest.mark.parametrize("role", [UserRole.admin, UserRole.cadastros, UserRole.produtos])
def test_papel_interno_pode_atribuir_carteira(role):
    dados = sanitize_client_update_fields({"rep_id": uuid.uuid4()}, _user(role))
    assert "rep_id" in dados


def test_representante_nao_reatribui_carteira():
    """Senão um representante puxaria para si o cliente de outro."""
    dados = sanitize_client_update_fields(
        {"rep_id": uuid.uuid4()}, _user(UserRole.representante, rep_id=uuid.uuid4())
    )
    assert "rep_id" not in dados


def test_conta_de_cliente_final_nao_reatribui_carteira():
    dados = sanitize_client_update_fields(
        {"rep_id": uuid.uuid4()}, _user(UserRole.cliente, linked_id=uuid.uuid4())
    )
    assert "rep_id" not in dados


def _db_com_representante(existe: bool):
    """Sessão mockada: `_validated_rep_id` só faz um SELECT de existência."""
    resultado = AsyncMock()
    resultado.scalar_one_or_none = lambda: uuid.uuid4() if existe else None
    db = AsyncMock()
    db.execute.return_value = resultado
    return db


class TestCarteiraNoCadastro:
    """Cadastro e edição precisam concordar sobre quem decide a carteira.

    Discordavam: o POST aceitava `rep_id` de qualquer papel que não fosse
    representante (inclusive do vendedor interno), enquanto o PATCH só aceitava
    de `COMMERCIAL_ROLES`. Quem gravasse errado no cadastro não tinha conserto.
    """

    @pytest.mark.parametrize("role", sorted(COMMERCIAL_ROLES, key=str))
    def test_papel_comercial_escolhe_a_carteira(self, role):
        rep = uuid.uuid4()
        resolvido = asyncio.run(
            _resolved_rep_id({"rep_id": rep}, _user(role), _db_com_representante(True))
        )
        assert resolvido == rep

    def test_vendedor_interno_nao_escolhe_a_carteira(self):
        """Mesma regra do PATCH: cadastra sem carteira, comercial corrige."""
        resolvido = asyncio.run(
            _resolved_rep_id(
                {"rep_id": uuid.uuid4()},
                _user(UserRole.vendedor),
                _db_com_representante(True),
            )
        )
        assert resolvido is None

    def test_representante_fica_com_a_propria_carteira(self):
        propria = uuid.uuid4()
        resolvido = asyncio.run(
            _resolved_rep_id(
                {"rep_id": uuid.uuid4()},  # tenta a de outro
                _user(UserRole.representante, rep_id=propria),
                _db_com_representante(True),
            )
        )
        assert resolvido == propria

    def test_representante_sem_registro_recebe_400(self):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                _resolved_rep_id(
                    {}, _user(UserRole.representante), _db_com_representante(True)
                )
            )
        assert exc.value.status_code == 400

    def test_carteira_inexistente_recebe_404(self):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                _resolved_rep_id(
                    {"rep_id": uuid.uuid4()},
                    _user(UserRole.admin),
                    _db_com_representante(False),
                )
            )
        assert exc.value.status_code == 404


class TestQuemCadastraCliente:
    """A lista do POST e a de quem decide a carteira precisam se sustentar.

    Elas divergiram: `cadastros` e `produtos` decidiam carteira e teto de
    desconto na edição, mas levavam 403 ao cadastrar — decidiam sobre um
    registro que não conseguiam criar.
    """

    @pytest.mark.parametrize("role", sorted(COMMERCIAL_ROLES, key=str))
    def test_quem_decide_a_carteira_consegue_cadastrar(self, role):
        assert role in _CREATE_CLIENT_ROLES

    @pytest.mark.parametrize("role", sorted(_CREATE_CLIENT_ROLES, key=str))
    def test_papeis_do_cadastro_passam_no_guard(self, role):
        assert _enforce_roles(_user(role), frozenset(_CREATE_CLIENT_ROLES))

    def test_conta_de_cliente_final_nao_cadastra(self):
        with pytest.raises(HTTPException) as exc:
            _enforce_roles(
                _user(UserRole.cliente, linked_id=uuid.uuid4()),
                frozenset(_CREATE_CLIENT_ROLES),
            )
        assert exc.value.status_code == 403

    def test_cliente_legado_com_role_vendedor_nao_cadastra(self):
        """SEC-01: `vendedor`+linked_id vale como cliente, não como operador."""
        with pytest.raises(HTTPException) as exc:
            _enforce_roles(
                _user(UserRole.vendedor, linked_id=uuid.uuid4()),
                frozenset(_CREATE_CLIENT_ROLES),
            )
        assert exc.value.status_code == 403
