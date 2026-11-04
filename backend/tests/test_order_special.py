from decimal import Decimal
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routers.orders import (
    _calculate_special_order_line,
    _resolve_special_code,
    _special_description,
)
from app.schemas.order import OrderItemCreate


def test_especial_calcula_percentagem_positiva_e_negativa_com_arredondamento():
    assert _calculate_special_order_line(
        base_price=Decimal("10.005"), qty=1, special_percent=Decimal("15.00"),
        tax_rate=0, product_code="PAI",
    )[:3] == (Decimal("11.51"), Decimal("0"), Decimal("11.51"))
    assert _calculate_special_order_line(
        base_price=Decimal("100.00"), qty=2, special_percent=Decimal("-20.00"),
        tax_rate=0, product_code="PAI",
    )[:3] == (Decimal("80.00"), Decimal("0"), Decimal("160.00"))


@pytest.mark.parametrize("value", [Decimal("-100"), Decimal("1000.01")])
def test_limites_de_percentagem_especial(value):
    with pytest.raises((ValidationError, HTTPException)):
        OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=value)


def test_percentagem_especial_zero_e_menos_cem_quase_ok():
    assert OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=0).special_percent == 0
    assert OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=Decimal("-99.99"))


def test_codigos_especiais_sao_sequenciais_e_nao_sao_o_pai():
    used = set()
    first = _resolve_special_code(OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=0), "PAI", used)
    second = _resolve_special_code(OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=0), "PAI", used)
    assert (first, second) == ("PAI-E1", "PAI-E2")
    assert first != "PAI" and second != "PAI"


def test_codigo_enviado_precisa_ser_do_pai_e_nao_repetir():
    used = {"PAI-E1"}
    with pytest.raises(HTTPException):
        _resolve_special_code(OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=0, special_code="OUTRO-E1"), "PAI", used)
    with pytest.raises(HTTPException):
        _resolve_special_code(OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=0, special_code="PAI-E1"), "PAI", used)


def test_schema_exige_consistencia_e_desconto_zero():
    with pytest.raises(ValidationError):
        OrderItemCreate(product_code="PAI", qty=1, is_special=True, special_percent=1, discount=1)
    with pytest.raises(ValidationError):
        OrderItemCreate(product_code="PAI", qty=1, special_percent=1)
    assert _special_description("Mesa") == "Mesa - ESPECIAL"
