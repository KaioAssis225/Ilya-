"""Vínculo cliente↔representante (carteira).

Sem `rep_id` no cadastro, um cliente criado por admin/cadastros nascia órfão
e o representante levava 403 ao faturar para ele, sem conserto pela API —
armadilha real num evento onde alguém cadastra clientes pela conta central.
Reatribuir carteira, porém, é decisão comercial: representante não escolhe.
"""
import uuid

import pytest

from app.api.deps import sanitize_client_update_fields
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
