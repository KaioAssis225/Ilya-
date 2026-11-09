"""TECIDO FORNECIDO (Portugal): constantes e regras puras da opção.

Chamado por `api/routers/orders.py` (preço e snapshot do item), `products.py`
(oferta da opção no catálogo) e `markets.py` (importação). A opção só existe nas
aplicações da categoria de tecidos IBTW de produtos EU que têm dados em
`product_supplied_fabric`; o preço e a metragem vêm SEMPRE do banco.
"""
from decimal import ROUND_HALF_UP, Decimal

# Código da categoria de opcionais "Tecidos IBTW" do mercado EU (ver
# alembic optional_brands_r25_20261026). Tecido fornecido é oferecido nas
# aplicações dessa categoria.
SUPPLIED_FABRIC_CATEGORY = "TECIDOS_IBTW"
SUPPLIED_FABRIC_MARKET = "EU"
# Nome gravado no snapshot da escolha (optional_name), como o "Customizado".
SUPPLIED_FABRIC_NAME = "TECIDO FORNECIDO"
SUPPLIED_FABRIC_NAME_EN = "SUPPLIED FABRIC"

PRICE_LIST_CODES = ("lojista", "corporativo", "pvp", "arquiteto")

_CENT = Decimal("0.01")


def round_money(value: Decimal | str | float) -> Decimal:
    """Arredonda para 2 casas em ROUND_HALF_UP (a planilha traz muitas casas)."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
