"""IVA por grupo (Portugal) — só exibição.

O IVA continua aprovado por produto em `product_markets` (EUROPA-MULTIMERCADO.md);
o grupo apenas resume as taxas aprovadas dos produtos dos seus subgrupos e
quantos ainda aguardam aprovação. Nada aqui altera cálculo de pedido.
"""
import uuid
from decimal import Decimal

from app.api.routers.product_groups import summarize_group_vat

G1 = uuid.uuid4()
G2 = uuid.uuid4()


def test_taxas_aprovadas_distintas_ordenadas_e_pendentes_contados():
    rows = [
        (G1, Decimal("23.00"), "approved", 4),
        (G1, Decimal("6.00"), "approved", 1),
        (G1, Decimal("23.00"), "approved", 2),
        (G1, None, "pending", 3),
        (G2, Decimal("23.00"), "pending", 2),
    ]
    summary = {item.group_id: item for item in summarize_group_vat(rows)}

    assert summary[G1].approved_rates == [Decimal("6.00"), Decimal("23.00")]
    assert summary[G1].approved_products == 7
    assert summary[G1].pending_products == 3

    # Taxa informada mas não aprovada não aparece como IVA do grupo.
    assert summary[G2].approved_rates == []
    assert summary[G2].approved_products == 0
    assert summary[G2].pending_products == 2


def test_zero_aprovado_e_taxa_valida():
    summary = summarize_group_vat([(G1, Decimal("0.00"), "approved", 1)])
    assert summary[0].approved_rates == [Decimal("0.00")]
    assert summary[0].approved_products == 1


def test_sem_linhas_sem_resumo():
    assert summarize_group_vat([]) == []
