"""Regressões do filtro de subgrupo no catálogo de produtos."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.routers.products import _normalized_product_type_value
from app.schemas.product import ProductCreate, ProductUpdate


def _product_payload(**overrides):
    payload = {
        "product_code": "BAN0001",
        "description": "Banqueta de teste",
        "type": "Banqueta",
        "altura": Decimal("1"),
        "largura": Decimal("1"),
        "profundidade": Decimal("1"),
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Banqueta", "banqueta"),
        ("BANQUETA", "banqueta"),
        (" Banqueta ", "banqueta"),
        ("Banquetas", "banqueta"),
    ],
)
def test_normalized_product_type_value(value, expected):
    assert _normalized_product_type_value(value) == expected


def test_product_create_remove_espacos_do_tipo():
    product = ProductCreate.model_validate(_product_payload(type="  Banqueta  "))
    assert product.type == "Banqueta"


def test_product_update_remove_espacos_do_tipo():
    product = ProductUpdate.model_validate({"type": "  Banquetas  "})
    assert product.type == "Banquetas"


def test_product_type_vazio_e_rejeitado():
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(_product_payload(type="   "))
