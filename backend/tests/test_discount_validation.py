"""Testes unitarios do Bloco 69 (Controle Dinamico de Desconto Maximo).

Mocka Client/Representative com limites distintos (SimpleNamespace) para
validar a resolucao dinamica de teto de desconto por role, sem depender de
banco de dados.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers.orders import _resolve_max_discount, _validate_discount
from app.models.user import UserRole


def _user(role: UserRole, linked_id=None) -> SimpleNamespace:
    # linked_id é lido por is_client_account() dentro de _resolve_max_discount (SEC-01).
    return SimpleNamespace(role=role, linked_id=linked_id)


def _client(max_discount: str) -> SimpleNamespace:
    return SimpleNamespace(max_discount=Decimal(max_discount))


def _rep(max_discount: str) -> SimpleNamespace:
    return SimpleNamespace(max_discount=Decimal(max_discount))


class TestResolveMaxDiscount:
    def test_admin_sempre_cem_por_cento(self):
        assert _resolve_max_discount(_user(UserRole.admin), _client("0.00"), None) == 100.0

    def test_cadastros_e_produtos_sempre_cem_por_cento(self):
        assert _resolve_max_discount(_user(UserRole.cadastros), _client("5.00"), None) == 100.0
        assert _resolve_max_discount(_user(UserRole.produtos), _client("5.00"), _rep("20.00")) == 100.0

    def test_representante_usa_limite_do_proprio_representante(self):
        rep = _rep("22.50")
        assert _resolve_max_discount(_user(UserRole.representante), _client("0.00"), rep) == 22.5

    def test_representante_sem_registro_associado_cai_para_zero(self):
        assert _resolve_max_discount(_user(UserRole.representante), _client("0.00"), None) == 0.0

    def test_vendedor_usa_limite_do_proprio_cliente(self):
        client = _client("8.00")
        assert _resolve_max_discount(_user(UserRole.vendedor), client, None) == 8.0

    def test_representantes_com_limites_distintos_nao_se_confundem(self):
        rep_a = _rep("10.00")
        rep_b = _rep("35.00")
        assert _resolve_max_discount(_user(UserRole.representante), _client("0.00"), rep_a) == 10.0
        assert _resolve_max_discount(_user(UserRole.representante), _client("0.00"), rep_b) == 35.0

    def test_clientes_com_limites_distintos_nao_se_confundem(self):
        client_a = _client("0.00")
        client_b = _client("12.00")
        assert _resolve_max_discount(_user(UserRole.vendedor), client_a, None) == 0.0
        assert _resolve_max_discount(_user(UserRole.vendedor), client_b, None) == 12.0


class TestValidateDiscount:
    def test_desconto_dentro_do_limite_nao_levanta_erro(self):
        _validate_discount(discount=10.0, max_discount=15.0, product_code="ABC123")

    def test_desconto_no_limite_exato_e_permitido(self):
        _validate_discount(discount=15.0, max_discount=15.0, product_code="ABC123")

    def test_desconto_acima_do_limite_levanta_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_discount(discount=20.0, max_discount=15.0, product_code="ABC123")
        assert exc_info.value.status_code == 422
        assert "ABC123" in exc_info.value.detail

    def test_desconto_negativo_levanta_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_discount(discount=-1.0, max_discount=15.0, product_code="ABC123")
        assert exc_info.value.status_code == 422

    def test_vendedor_sem_desconto_configurado_nao_pode_dar_desconto(self):
        max_discount = _resolve_max_discount(_user(UserRole.vendedor), _client("0.00"), None)
        with pytest.raises(HTTPException):
            _validate_discount(discount=1.0, max_discount=max_discount, product_code="XYZ")

    def test_admin_pode_dar_cem_por_cento_de_desconto(self):
        max_discount = _resolve_max_discount(_user(UserRole.admin), _client("0.00"), None)
        _validate_discount(discount=100.0, max_discount=max_discount, product_code="XYZ")
