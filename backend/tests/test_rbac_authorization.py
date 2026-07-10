"""Matriz de autorização RBAC — SEC-01/SEC-02 (auditoria Codex 2026-07-10).

Prova, sem depender de banco, que uma conta de portal do cliente-final nunca
recebe permissão de operador interno, mesmo se ainda estiver com a role legada
`vendedor` + linked_id (antes da migração 0028 propagar).

`require_roles` devolve uma dependency que, em produção, recebe `current_user`
via Depends(get_current_user). Aqui chamamos a dependency diretamente passando
`current_user=...`, o que exercita apenas a lógica de autorização.
"""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import require_roles, is_client_account, is_internal_operator
from app.models.user import UserRole


def _user(role: UserRole, linked_id=None, rep_id=None) -> SimpleNamespace:
    return SimpleNamespace(role=role, linked_id=linked_id, rep_id=rep_id)


_CLIENT_ID = uuid.uuid4()
_REP_ID = uuid.uuid4()

# Contas de portal do cliente-final nas duas formas: role nova e legada.
CLIENTE_NOVO = _user(UserRole.cliente, linked_id=_CLIENT_ID)
CLIENTE_LEGADO = _user(UserRole.vendedor, linked_id=_CLIENT_ID)
# Operador interno de vendas: vendedor SEM vínculo de cliente.
VENDEDOR_INTERNO = _user(UserRole.vendedor)
REPRESENTANTE = _user(UserRole.representante, linked_id=_REP_ID, rep_id=_REP_ID)
ADMIN = _user(UserRole.admin)


class TestClassificacaoDeConta:
    def test_role_cliente_e_conta_de_cliente(self):
        assert is_client_account(CLIENTE_NOVO) is True

    def test_vendedor_com_linked_id_e_conta_de_cliente_legada(self):
        assert is_client_account(CLIENTE_LEGADO) is True

    def test_vendedor_sem_linked_id_nao_e_conta_de_cliente(self):
        assert is_client_account(VENDEDOR_INTERNO) is False

    def test_representante_nao_e_conta_de_cliente(self):
        assert is_client_account(REPRESENTANTE) is False

    def test_vendedor_sem_vinculo_e_operador_interno(self):
        assert is_internal_operator(VENDEDOR_INTERNO) is True

    def test_cliente_nao_e_operador_interno(self):
        assert is_internal_operator(CLIENTE_NOVO) is False
        assert is_internal_operator(CLIENTE_LEGADO) is False


class TestCatalogoBloqueiaCliente:
    """`_ADMIN_VENDEDOR` = require_roles(admin, vendedor) protege mutações de catálogo."""

    catalog_dep = staticmethod(require_roles(UserRole.admin, UserRole.vendedor))

    def test_cliente_novo_nao_altera_catalogo(self):
        with pytest.raises(HTTPException) as e:
            self.catalog_dep(current_user=CLIENTE_NOVO)
        assert e.value.status_code == 403

    def test_cliente_legado_vendedor_com_linked_id_nao_altera_catalogo(self):
        # Núcleo do SEC-01: mesmo com a role legada `vendedor`, o linked_id o rebaixa.
        with pytest.raises(HTTPException) as e:
            self.catalog_dep(current_user=CLIENTE_LEGADO)
        assert e.value.status_code == 403

    def test_operador_interno_altera_catalogo(self):
        assert self.catalog_dep(current_user=VENDEDOR_INTERNO) is VENDEDOR_INTERNO

    def test_admin_altera_catalogo(self):
        assert self.catalog_dep(current_user=ADMIN) is ADMIN

    def test_representante_nao_altera_catalogo(self):
        with pytest.raises(HTTPException) as e:
            self.catalog_dep(current_user=REPRESENTANTE)
        assert e.value.status_code == 403


class TestLeituraCatalogoPermiteCliente:
    """`_ANY` de catálogo inclui `cliente` para o portal montar orçamento."""

    read_dep = staticmethod(require_roles(
        UserRole.admin, UserRole.vendedor, UserRole.representante, UserRole.cliente
    ))

    def test_cliente_novo_le_catalogo(self):
        assert self.read_dep(current_user=CLIENTE_NOVO) is CLIENTE_NOVO

    def test_cliente_legado_le_catalogo(self):
        # Rebaixado para cliente, mas cliente está na lista de leitura → permitido.
        assert self.read_dep(current_user=CLIENTE_LEGADO) is CLIENTE_LEGADO

    def test_representante_le_catalogo(self):
        assert self.read_dep(current_user=REPRESENTANTE) is REPRESENTANTE


class TestAdminOnlyBloqueiaTodosMenosAdmin:
    admin_dep = staticmethod(require_roles(UserRole.admin))

    def test_cliente_bloqueado(self):
        with pytest.raises(HTTPException):
            self.admin_dep(current_user=CLIENTE_NOVO)

    def test_vendedor_interno_bloqueado(self):
        with pytest.raises(HTTPException):
            self.admin_dep(current_user=VENDEDOR_INTERNO)

    def test_admin_permitido(self):
        assert self.admin_dep(current_user=ADMIN) is ADMIN
