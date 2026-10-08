"""Aprovação de IVA em lote pelo grupo (Portugal).

Decisão de 08/10/2026: o botão Editar do grupo EU aplica e aprova uma taxa de
IVA em todos os produtos dos subgrupos do grupo. Continua exigindo a permissão
fiscal do vínculo EU (can_approve_tax) e cada produto registra quem aprovou e
quando — o que muda é poder aprovar o conjunto de uma vez.
"""
import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routers.markets import GroupVatRequest, approve_europe_group_vat
from app.core.markets import MARKETS, MarketPrincipal
from app.models.product_group import ProductGroup


def _principal(market: str, can_approve_tax: bool) -> MarketPrincipal:
    access = SimpleNamespace(role="admin", can_approve_tax=can_approve_tax)
    return MarketPrincipal(user=SimpleNamespace(id=uuid.uuid4()), market=MARKETS[market], access=access)


def _db(group: ProductGroup | None, rowcount: int = 0) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.get.return_value = group
    db.execute.return_value = SimpleNamespace(rowcount=rowcount)
    return db


def _eu_group() -> ProductGroup:
    return ProductGroup(id=uuid.uuid4(), market_code="EU", name="Interior", ipi=Decimal("0"))


def _run(principal, db, group_id=None, rate="23"):
    return asyncio.run(approve_europe_group_vat(
        group_id=group_id or uuid.uuid4(),
        body=GroupVatRequest(vat_rate=Decimal(rate)),
        db=db,
        principal=principal,
    ))


def test_sem_permissao_fiscal_recebe_403_e_nao_grava():
    db = _db(_eu_group())
    with pytest.raises(HTTPException) as exc:
        _run(_principal("EU", can_approve_tax=False), db)
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_no_brasil_nao_existe_iva_por_grupo():
    db = _db(_eu_group())
    with pytest.raises(HTTPException) as exc:
        _run(_principal("BR", can_approve_tax=True), db)
    assert exc.value.status_code == 403
    db.commit.assert_not_awaited()


def test_grupo_de_outro_mercado_responde_404():
    br_group = ProductGroup(id=uuid.uuid4(), market_code="BR", name="Moveis", ipi=Decimal("3.25"))
    db = _db(br_group)
    with pytest.raises(HTTPException) as exc:
        _run(_principal("EU", can_approve_tax=True), db)
    assert exc.value.status_code == 404
    db.execute.assert_not_awaited()


def test_aprova_e_devolve_quantos_produtos_foram_aprovados():
    group = _eu_group()
    db = _db(group, rowcount=5)
    result = _run(_principal("EU", can_approve_tax=True), db, group_id=group.id, rate="6")
    assert result["approved_products"] == 5
    assert result["vat_rate"] == Decimal("6")
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("rate", ["-1", "100.01"])
def test_taxa_fora_de_0_a_100_e_recusada(rate):
    with pytest.raises(ValidationError):
        GroupVatRequest(vat_rate=Decimal(rate))
