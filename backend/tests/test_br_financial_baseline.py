"""Linha de base financeira BR protegida antes das próximas migrations."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers.orders import (
    _calculate_order_line,
    _price_for_profile,
)


def test_perfil_do_cliente_escolhe_o_preco_faturado():
    product = SimpleNamespace(
        price_lojista=Decimal("120.40"),
        price_corporativo=Decimal("97.35"),
    )

    assert _price_for_profile(product, "lojista") == Decimal("120.40")
    assert _price_for_profile(product, "corporativo") == Decimal("97.35")


def test_linha_br_aplica_desconto_arredondamento_e_ipi():
    result = _calculate_order_line(
        unit_price=Decimal("19.99"),
        qty=3,
        discount=Decimal("10.00"),
        max_discount=Decimal("15.00"),
        product_code="BR-001",
        tax_rate=Decimal("5.00"),
    )

    assert result == (
        Decimal("19.99"),
        Decimal("10.00"),
        Decimal("53.97"),
        Decimal("5.00"),
        Decimal("2.70"),
    )
    assert result[2] + result[4] == Decimal("56.67")


def test_arredondamento_monetario_br_e_half_up_em_cada_linha():
    result = _calculate_order_line(
        unit_price=Decimal("10.005"),
        qty=1,
        discount=Decimal("0"),
        max_discount=Decimal("0"),
        product_code="BR-ROUND",
        tax_rate=Decimal("5"),
    )

    assert result[0] == Decimal("10.01")
    assert result[2] == Decimal("10.01")
    assert result[4] == Decimal("0.50")


def test_linha_br_rejeita_desconto_acima_do_teto():
    with pytest.raises(HTTPException) as exc:
        _calculate_order_line(
            unit_price=Decimal("100"),
            qty=1,
            discount=Decimal("15.01"),
            max_discount=Decimal("15.00"),
            product_code="BR-LIMIT",
            tax_rate=Decimal("5"),
        )

    assert exc.value.status_code == 422

