"""Matriz de autorização RBAC — SEC-01/SEC-02 (auditoria Codex 2026-07-10).

Prova, sem depender de banco, que uma conta de portal do cliente-final nunca
recebe permissão de operador interno, mesmo se ainda estiver com a role legada
`vendedor` + linked_id (antes da migração 0028 propagar).

`require_roles` devolve uma dependency que, em produção, recebe `current_user`
via Depends(get_current_user). Aqui chamamos a dependency diretamente passando
`current_user=...`, o que exercita apenas a lógica de autorização.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.deps import (
    require_directory_access,
    require_order_access,
    require_roles,
    is_client_account,
    is_internal_operator,
)
from app.api.routers.orders import (
    CancelPayload,
    FinalizePayload,
    _can_create_order,
    _can_operate_order,
    cancel_order,
    create_order,
    finalize_order,
    update_order,
)
from app.models.user import UserRole
from app.schemas.order import OrderUpdate


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
CADASTROS = _user(UserRole.cadastros)
PRODUTOS = _user(UserRole.produtos)
EXECUTIVO = _user(UserRole.executivo)


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


class TestAcessoAosDiretoriosComerciais:
    @pytest.mark.parametrize(
        "user",
        [
            ADMIN,
            VENDEDOR_INTERNO,
            REPRESENTANTE,
            CLIENTE_NOVO,
            CLIENTE_LEGADO,
            CADASTROS,
            PRODUTOS,
        ],
    )
    def test_papeis_comerciais_permitidos(self, user):
        assert require_directory_access(current_user=user) is user

    def test_executivo_bloqueado(self):
        with pytest.raises(HTTPException) as exc:
            require_directory_access(current_user=EXECUTIVO)
        assert exc.value.status_code == 403


class TestAcessoAPedidos:
    @pytest.mark.parametrize(
        "user",
        [
            ADMIN,
            VENDEDOR_INTERNO,
            REPRESENTANTE,
            CLIENTE_NOVO,
            CLIENTE_LEGADO,
            PRODUTOS,
        ],
    )
    def test_papeis_de_pedidos_permitidos(self, user):
        assert require_order_access(current_user=user) is user

    @pytest.mark.parametrize("user", [EXECUTIVO, CADASTROS])
    def test_papeis_sem_acesso_bloqueados(self, user):
        with pytest.raises(HTTPException) as exc:
            require_order_access(current_user=user)
        assert exc.value.status_code == 403


class TestOperacaoDoCicloDoPedido:
    """Editar / finalizar / cancelar — guard compartilhado dos três handlers.

    Ler e criar pedido são mais amplos que operar: a conta de cliente entra em
    `require_order_access` e em `_can_create_order`, mas nunca opera (SEC-02).
    """

    @pytest.mark.parametrize(
        "user",
        [ADMIN, VENDEDOR_INTERNO, REPRESENTANTE],
    )
    def test_papeis_operadores_permitidos(self, user):
        assert _can_operate_order(user) is True

    @pytest.mark.parametrize(
        "user",
        [CLIENTE_NOVO, CLIENTE_LEGADO, CADASTROS, PRODUTOS, EXECUTIVO],
    )
    def test_papeis_nao_operadores_bloqueados(self, user):
        assert _can_operate_order(user) is False

    def test_cliente_legado_nao_opera_mesmo_com_role_vendedor(self):
        """O legado `vendedor`+linked_id lê pedidos, mas não edita/cancela."""
        assert require_order_access(current_user=CLIENTE_LEGADO) is CLIENTE_LEGADO
        assert _can_operate_order(CLIENTE_LEGADO) is False


class TestCriacaoDePedido:
    @pytest.mark.parametrize(
        "user",
        [ADMIN, VENDEDOR_INTERNO, REPRESENTANTE, CLIENTE_NOVO, CLIENTE_LEGADO],
    )
    def test_papeis_comerciais_permitidos(self, user):
        assert _can_create_order(user) is True

    @pytest.mark.parametrize("user", [CADASTROS, PRODUTOS, EXECUTIVO])
    def test_papeis_sem_decisao_comercial_bloqueados(self, user):
        assert _can_create_order(user) is False


class TestProdutosNaoMutaPedidos:
    """Prova o 403 nos quatro handlers, antes de qualquer acesso ao banco."""

    @staticmethod
    def _assert_forbidden(operation):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(operation)
        assert exc.value.status_code == 403

    def test_produtos_nao_cria_pedido(self):
        db = AsyncMock()
        self._assert_forbidden(create_order(
            payload=SimpleNamespace(),
            db=db,
            current_user=PRODUTOS,
            principal=SimpleNamespace(),
        ))
        db.execute.assert_not_awaited()

    def test_produtos_nao_edita_pedido(self):
        db = AsyncMock()
        self._assert_forbidden(update_order(
            order_id=uuid.uuid4(),
            payload=OrderUpdate(notes="não permitido"),
            db=db,
            current_user=PRODUTOS,
            principal=SimpleNamespace(),
        ))
        db.execute.assert_not_awaited()

    def test_produtos_nao_finaliza_pedido(self):
        db = AsyncMock()
        self._assert_forbidden(finalize_order(
            order_id=uuid.uuid4(),
            payload=FinalizePayload(),
            db=db,
            current_user=PRODUTOS,
        ))
        db.execute.assert_not_awaited()

    def test_produtos_nao_cancela_pedido(self):
        db = AsyncMock()
        self._assert_forbidden(cancel_order(
            order_id=uuid.uuid4(),
            payload=CancelPayload(),
            db=db,
            current_user=PRODUTOS,
        ))
        db.execute.assert_not_awaited()
