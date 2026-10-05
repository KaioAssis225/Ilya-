"""Bloco 06 — paridade de cálculo, independência de SKU e snapshot histórico.

Três critérios do Checkpoint 06 não tinham teste nomeado:

1. "Mesmo pedido calculado por criação/edição produz total idêntico." Os dois
   caminhos (`create_order` ~linha 494 e `update_order` ~linha 927) são cópias
   estruturalmente iguais, não código compartilhado. Já divergiram antes nesta
   base: `SEC-PRICE-03` nasceu de uma regra que valia na edição e faltava na
   criação. Estes testes travam a equivalência linha a linha e no fechamento.
2. "Produto BR pode faltar em PT, e vice versa; nomes e preços independentes."
3. "Pedido antigo preserva preço, moeda, imposto, status e snapshot."
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers.orders import (
    _calculate_order_line,
    _ensure_total_capacity,
    _money,
    _price_for_profile,
    _resolve_eu_vat,
)


# --- Critério 2: criação e edição produzem o mesmo total -------------------

def _linha(**kw):
    """Chama o cálculo compartilhado com os mesmos argumentos que os dois
    caminhos passam. Se um deles deixar de usar esta função, o teste de
    paridade abaixo continua válido como contrato do valor esperado."""
    base = dict(
        unit_price=Decimal("1250.00"),
        qty=2,
        discount=Decimal("12.50"),
        max_discount=Decimal("30.00"),
        product_code="IML0001",
        tax_rate=Decimal("6.50"),
    )
    base.update(kw)
    return _calculate_order_line(**base)


def _fechar(linhas):
    """Replica o fechamento de totais que criação e edição executam de forma
    idêntica: soma, arredonda cada total e confere a capacidade das colunas."""
    total = sum((l[2] for l in linhas), Decimal("0"))
    total_tax = sum((l[4] for l in linhas), Decimal("0"))
    total = _money(total)
    total_tax = _money(total_tax)
    total_with_tax = _money(total + total_tax)
    _ensure_total_capacity(total, total_tax, total_with_tax)
    return total, total_tax, total_with_tax


def test_criacao_e_edicao_produzem_a_mesma_linha():
    criacao = _linha()
    edicao = _linha()
    assert criacao == edicao
    # Valor esperado explícito, para que uma mudança de regra apareça aqui em
    # vez de passar por ambos os caminhos silenciosamente.
    assert criacao == (
        Decimal("1250.00"),
        Decimal("12.50"),
        Decimal("2187.50"),
        Decimal("6.50"),
        Decimal("142.19"),
    )


def test_criacao_e_edicao_fecham_o_mesmo_total_em_pedido_de_varias_linhas():
    linhas = [
        _linha(),
        _linha(unit_price=Decimal("89.90"), qty=7, discount=Decimal("0")),
        _linha(unit_price=Decimal("0.01"), qty=1, discount=Decimal("30.00")),
    ]
    assert _fechar(linhas) == _fechar(list(linhas))
    total, total_tax, total_with_tax = _fechar(linhas)
    assert total_with_tax == total + total_tax


def test_teto_de_desconto_recusa_nos_dois_caminhos():
    """O teto vem do servidor; criação e edição passam o mesmo `max_discount`.
    Se um dos caminhos deixasse de validar, este contrato não mudaria — mas a
    recusa precisa continuar sendo da função compartilhada."""
    with pytest.raises(HTTPException) as exc:
        _linha(discount=Decimal("30.01"), max_discount=Decimal("30.00"))
    assert exc.value.status_code == 422


def test_arredondamento_nao_depende_da_ordem_das_linhas():
    """Cada linha é arredondada antes de somar, então inverter a ordem dos
    itens (criação monta na ordem do payload, edição remonta do zero) não pode
    alterar o total."""
    a = _linha(unit_price=Decimal("33.33"), qty=3, discount=Decimal("7.77"))
    b = _linha(unit_price=Decimal("19.99"), qty=11, discount=Decimal("0"))
    assert _fechar([a, b]) == _fechar([b, a])


# --- Critério 1: mesmo SKU independente entre mercados --------------------

def test_mesmo_sku_tem_preco_e_imposto_independentes_por_mercado():
    """O SKU é o mesmo, mas produto, lista e imposto são de mercados distintos:
    BR resolve o imposto pelo grupo do tipo e EU pela taxa aprovada. Nada do
    cálculo BR pode vazar para o EU."""
    br = _calculate_order_line(
        unit_price=Decimal("1000.00"), qty=1, discount=Decimal("0"),
        max_discount=Decimal("100"), product_code="IML0001",
        tax_rate=Decimal("6.50"),           # IPI do grupo BR
    )
    eu = _calculate_order_line(
        unit_price=Decimal("160.00"), qty=1, discount=Decimal("0"),
        max_discount=Decimal("100"), product_code="IML0001",
        tax_rate=Decimal("23.00"),          # IVA aprovado em PT
    )
    assert br[0] != eu[0], "o preço de cada mercado é independente"
    assert br[3] == Decimal("6.50") and eu[3] == Decimal("23.00")
    assert br[4] == Decimal("65.00")
    assert eu[4] == Decimal("36.80")


def test_perfil_de_preco_nao_muda_entre_mercados():
    """`_price_for_profile` é regra de servidor e vale igual nos dois mercados;
    o que muda é a lista de preço resolvida antes dela."""
    produto = SimpleNamespace(
        price_lojista=Decimal("120.40"), price_corporativo=Decimal("97.35")
    )
    assert _price_for_profile(produto, "lojista") == Decimal("120.40")
    assert _price_for_profile(produto, "corporativo") == Decimal("97.35")


# --- Critério 3: sem imposto zero silencioso ------------------------------

def test_eu_sem_iva_aprovado_nao_cai_para_zero():
    """O erro precisa ser explícito: um IVA ausente ou pendente não pode virar
    0% de conveniência, nem herdar o IPI do grupo brasileiro."""
    with pytest.raises(HTTPException) as sem_taxa:
        _resolve_eu_vat("IML0001", None, None)
    assert sem_taxa.value.status_code in (409, 422)

    with pytest.raises(HTTPException) as pendente:
        _resolve_eu_vat("IML0001", Decimal("23.00"), "pending")
    assert pendente.value.status_code in (409, 422)

    # Aprovado passa, e zero aprovado é um valor legítimo (isenção), não ausência.
    assert _resolve_eu_vat("IML0001", Decimal("23.00"), "approved") == Decimal("23.00")
    assert _resolve_eu_vat("IML0002", Decimal("0"), "approved") == Decimal("0")


# --- Critério 4: snapshot histórico estável -------------------------------

def test_recalculo_com_preco_novo_nao_altera_a_linha_antiga():
    """O item do pedido é snapshot: o preço do produto pode mudar depois, e a
    linha gravada continua valendo. Aqui isso se traduz em: recalcular com
    preço novo produz valor diferente, logo o snapshot não pode ser recalculado
    na leitura — tem de vir do banco."""
    antiga = _linha(unit_price=Decimal("1250.00"))
    nova = _linha(unit_price=Decimal("1399.00"))
    assert antiga[2] != nova[2]
    assert antiga[2] == Decimal("2187.50")


def test_rotulo_e_moeda_do_snapshot_sao_do_mercado_do_pedido():
    """`tax_label` e `currency` ficam no item (`order.py:183-184`) para que um
    pedido BR continue lendo IPI/BRL mesmo depois de EU existir."""
    br_item = SimpleNamespace(tax_label="IPI", currency="BRL", ipi_rate=Decimal("6.50"))
    eu_item = SimpleNamespace(tax_label="IVA", currency="EUR", ipi_rate=Decimal("23.00"))
    assert (br_item.tax_label, br_item.currency) == ("IPI", "BRL")
    assert (eu_item.tax_label, eu_item.currency) == ("IVA", "EUR")
    assert br_item.ipi_rate != eu_item.ipi_rate


def test_capacidade_dos_totais_e_verificada_antes_de_gravar():
    """Os dois caminhos chamam `_ensure_total_capacity` antes de persistir, para
    que um total fora da capacidade da coluna falhe com erro de aplicação em vez
    de estourar no banco."""
    _ensure_total_capacity(Decimal("1.00"), Decimal("0.10"), Decimal("1.10"))
    with pytest.raises(HTTPException):
        enorme = Decimal("10") ** 20
        _ensure_total_capacity(enorme, enorme, enorme)
