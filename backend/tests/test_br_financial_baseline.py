"""Linha de base financeira BR protegida antes das próximas migrations."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers.orders import (
    _calculate_order_line,
    _price_for_profile,
    _resolve_br_ipi,
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



def _tipo(nome="BANQUETA", ipi="3.25"):
    return SimpleNamespace(name=nome, group=SimpleNamespace(ipi=Decimal(ipi)))


def test_ipi_vem_do_grupo_do_tipo():
    assert _resolve_br_ipi("IBQ0014", _tipo()) == Decimal("3.25")


def test_ipi_zero_cadastrado_e_aceito():
    """Zero legitimo nao e ausencia de dado.

    Grupo fiscal com aliquota 0 e cadastro deliberado e deve faturar zero. A
    guarda abaixo recusa a FALTA do vinculo, nao a aliquota zerada -- confundir
    as duas coisas quebraria quem hoje vende isento.
    """
    assert _resolve_br_ipi("BR-ISENTO", _tipo(ipi="0")) == Decimal("0")


def test_tipo_nao_cadastrado_recusa_o_pedido():
    """Regressao do achado de 06/10: o IPI zero silencioso no BR.

    `products.type` e texto livre (String(50), sem FK), entao basta diferenca de
    caixa -- 'Banqueta' contra 'BANQUETA' -- para o tipo nao casar em
    `ProductType.name.in_(type_names)`. A conciliacao pos-corte achou 5 produtos
    nessa situacao, entre eles IBQ0014 e tres conjuntos de ombrelone.

    Antes, `product_type` nulo caia para `_ZERO` e o pedido era emitido com
    imposto zerado, sem nada no log. O EU ja recusava o caso equivalente
    (`_resolve_eu_vat`); o criterio "sem IPI zero silencioso" do Checkpoint 06
    valia so num dos dois mercados -- e e o BR que fatura.
    """
    with pytest.raises(HTTPException) as exc:
        _resolve_br_ipi("IBQ0014", None)
    assert exc.value.status_code == 422
    assert "tipo" in exc.value.detail.lower()


def test_tipo_sem_grupo_fiscal_recusa_o_pedido():
    """`product_types.group_id` e nullable: tipo pode existir sem grupo.

    Sem grupo nao existe aliquota a aplicar, entao zerar seria inventar uma.
    """
    sem_grupo = SimpleNamespace(name="CONJUNTO", group=None)
    with pytest.raises(HTTPException) as exc:
        _resolve_br_ipi("IOM1027 BA0103", sem_grupo)
    assert exc.value.status_code == 422
    assert "grupo" in exc.value.detail.lower()
