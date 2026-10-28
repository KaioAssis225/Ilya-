"""Testes unitários para funcionalidades de produtos por área (tapetes)."""

import pytest
from decimal import Decimal
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.area_products import area_from_dimensions, is_area_catalog, is_area_product
from app.api.routers.orders import (
    _format_area,
    _validate_item_quantity,
    _calculate_order_line,
)
from app.schemas.order import OrderItemCreate


# ---------- is_area_catalog ----------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Tapete", True),
        (" TAPETES ", True),
        ("Tápete", True),  # acento removido na normalização
        ("tapete", True),
        ("Tapeçaria", False),
        ("Ilya", False),
        ("", False),
        (None, False),
    ],
)
def test_is_area_catalog(name, expected):
    """Verifica a normalização e detecção de catálogos de tapete."""
    assert is_area_catalog(name) is expected


# ---------- is_area_product ----------

def test_is_area_product_true_para_tapete():
    """Produto com catálogo 'Tapete' deve ser reconhecido como área."""
    produto = SimpleNamespace(
        catalog=SimpleNamespace(name="Tapete")
    )
    assert is_area_product(produto) is True


def test_is_area_product_falso_para_catalogo_nao_tapete():
    """Produto com catálogo 'Ilya' não deve ser área."""
    produto = SimpleNamespace(
        catalog=SimpleNamespace(name="Ilya")
    )
    assert is_area_product(produto) is False


def test_is_area_product_falso_quando_catalogo_nulo():
    """Produto com catálogo None deve retornar False sem erro."""
    produto = SimpleNamespace(catalog=None)
    assert is_area_product(produto) is False


def test_is_area_product_falso_sem_atributo_catalog():
    """Objeto sem atributo catalog deve retornar False sem erro."""
    produto = SimpleNamespace(product_code="TP-1")
    assert is_area_product(produto) is False


# ---------- _format_area ----------

@pytest.mark.parametrize(
    "valor, esperado",
    [
        (Decimal("12.50"), "12,5"),
        (Decimal("10.00"), "10"),
        (Decimal("0.75"), "0,75"),
    ],
)
def test_format_area(valor, esperado):
    """Verifica a formatação brasileira de áreas."""
    assert _format_area(valor) == esperado


# ---------- _validate_item_quantity ----------

def _criar_produto(
    nome_catalogo="Tapete",
    area_limit_enabled=False,
    max_area_m2=None,
):
    """Cria um produto fake para os testes de validação."""
    return SimpleNamespace(
        product_code="TP-1",
        catalog=SimpleNamespace(name=nome_catalogo),
        area_limit_enabled=area_limit_enabled,
        max_area_m2=max_area_m2,
    )


def test_validate_item_quantity_nao_tapete_com_fracao_levanta_422():
    """Quantidade fracionária para produto não tapete deve resultar em 422."""
    produto = _criar_produto(nome_catalogo="Ilya")
    with pytest.raises(HTTPException) as excinfo:
        _validate_item_quantity(produto, Decimal("1.5"))
    assert excinfo.value.status_code == 422
    assert "deve ser um número inteiro" in excinfo.value.detail


@pytest.mark.parametrize("qty", [Decimal("2"), Decimal("2.00")])
def test_validate_item_quantity_nao_tapete_inteiro_retorna_false(qty):
    """Quantidade inteira para produto não tapete retorna False."""
    produto = _criar_produto(nome_catalogo="Ilya")
    assert _validate_item_quantity(produto, qty) is False


def test_validate_item_quantity_tapete_sem_limite_retorna_true():
    """Tapete sem limite de área ativo aceita qualquer quantidade."""
    produto = _criar_produto(nome_catalogo="Tapete")
    assert _validate_item_quantity(produto, Decimal("4.5")) is True


def test_validate_item_quantity_tapete_com_limite_excedido_levanta_422():
    """Tapete com limite ativo e quantidade acima do máximo deve dar 422."""
    produto = _criar_produto(
        nome_catalogo="Tapete",
        area_limit_enabled=True,
        max_area_m2=Decimal("10"),
    )
    with pytest.raises(HTTPException) as excinfo:
        _validate_item_quantity(produto, Decimal("10.01"))
    assert excinfo.value.status_code == 422
    assert "no máximo" in excinfo.value.detail
    assert "10 m²" in excinfo.value.detail


def test_validate_item_quantity_tapete_quantidade_igual_maximo_retorna_true():
    """Quantidade exatamente igual ao limite máximo deve ser permitida."""
    produto = _criar_produto(
        nome_catalogo="Tapete",
        area_limit_enabled=True,
        max_area_m2=Decimal("10"),
    )
    assert _validate_item_quantity(produto, Decimal("10")) is True


def test_validate_item_quantity_tapete_com_limite_ativado_por_sem_max_retorna_true():
    """Se o limite está ativo mas max_area_m2 é None, não deve gerar erro."""
    produto = _criar_produto(
        nome_catalogo="Tapete",
        area_limit_enabled=True,
        max_area_m2=None,
    )
    assert _validate_item_quantity(produto, Decimal("5.5")) is True


# ---------- _calculate_order_line ----------

def test_calculate_order_line_com_quantidade_decimal():
    """Cálculo correto para 4,5 m² com arredondamento monetário."""
    resultado = _calculate_order_line(
        unit_price=Decimal("172.31"),
        qty=Decimal("4.5"),
        discount=Decimal("0"),
        max_discount=Decimal("30"),
        product_code="TP-1",
        tax_rate=Decimal("23"),
    )
    # resultado: (rounded_unit_price, discount, subtotal, tax_rate, tax_value)
    assert resultado[2] == Decimal("775.40")  # subtotal com ROUND_HALF_UP
    assert resultado[4] == Decimal("178.34")  # imposto sobre o subtotal


# ---------- OrderItemCreate ----------

def test_order_item_create_qty_decimal_com_duas_casas_aceito():
    """Quantidade 4,50 é aceita pelo schema."""
    item = OrderItemCreate(product_code="TP-1", qty=Decimal("4.50"))
    assert item.qty == Decimal("4.50")


def test_order_item_create_qty_com_mais_de_duas_casas_rejeitado():
    """Quantidade com 3 casas decimais deve falhar na validação."""
    with pytest.raises(ValidationError):
        OrderItemCreate(product_code="TP-1", qty=Decimal("4.555"))


def test_order_item_create_qty_zero_rejeitado():
    """Quantidade zero viola gt=0."""
    with pytest.raises(ValidationError):
        OrderItemCreate(product_code="TP-1", qty=Decimal("0"))


# ---------- area_from_dimensions ----------

@pytest.mark.parametrize(
    "width, depth, expected",
    [
        (Decimal("2.05"), Decimal("2.05"), Decimal("4.20")),
        (Decimal("1.5"), Decimal("2.003"), Decimal("3.00")),
        (Decimal("0.05"), Decimal("0.05"), Decimal("0.01")),
    ],
)
def test_area_from_dimensions(width, depth, expected):
    """Área cobrada deve ser L×P arredondada a 2 casas com ROUND_HALF_UP."""
    assert area_from_dimensions(width, depth) == expected
