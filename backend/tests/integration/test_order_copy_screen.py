"""Copiar como orçamento novo: POST /orders com `copy_source_order_id`.

A tela de Orçamento abre preenchida a partir do pedido de origem e só cria ao
confirmar. Os itens que ainda apontam para um item da origem seguem as regras de
cópia (preço de hoje, desconto limitado, item que não pode ser copiado é pulado e
avisado); o que é novo na tela segue a criação normal. Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Catalog
from app.models.market import ProductPrice
from app.models.order_history import OrderHistory
from app.models.product import Product
from tests.factories import make_product, make_product_market, make_product_price
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _SKIP_SCOPE,
    _auth,
    _choice,
    _item,
    _post_order,
    _scenario,
    _seeded_price_list,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _source(client: AsyncClient, s: Scenario) -> dict:
    created = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black),
              qty=1, comment="linha um"),
        _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe),
              qty=2, comment="linha dois"),
    ])
    assert created.status_code == 201, created.text
    return created.json()


def _from_source(s: Scenario, source_item: dict, *choices: dict, **extra) -> dict:
    """Item como a tela o envia: o mesmo item da origem, apontando para ele."""
    return _item(
        s, *choices, qty=source_item["qty"], comment=source_item["comment"],
        source_order_item_id=source_item["id"], **extra,
    )


def _post_copy(client: AsyncClient, s: Scenario, source: dict, items: list[dict]):
    return client.post(
        "/api/v1/orders",
        json={
            "client_id": str(s.client_id), "items": items,
            "copy_source_order_id": source["id"],
        },
        headers=_auth(s.token),
    )


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_post_com_copy_source_cria_orcamento_novo_com_preco_de_hoje(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    s = await _scenario(db_session, market)
    source = await _source(client, s)
    second = next(i for i in source["items"] if i["qty"] == 2)

    await db_session.execute(
        update(ProductPrice).where(ProductPrice.product_id == s.product_id)
        .values(amount=Decimal("150.00"))
    )
    await db_session.commit()
    db_session.expunge_all()

    response = await _post_copy(client, s, source, [
        _from_source(s, second, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe)),
    ])
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied["id"] != source["id"] and copied["copy_skipped"] == []
    assert copied["is_finalized"] is False
    [item] = copied["items"]
    assert item["qty"] == 2 and item["comment"] == "linha dois"
    assert Decimal(item["unit_price"]) == Decimal("150.00")
    assert Decimal(copied["total_value"]) == Decimal("300.00")

    history = (await db_session.execute(
        select(OrderHistory.details).where(OrderHistory.order_id == uuid.UUID(copied["id"]))
        .execution_options(**_SKIP_SCOPE)
    )).scalars().all()
    assert history == [f"copiado de {source['code']}"]


async def test_item_da_copia_que_nao_pode_ser_copiado_e_pulado_e_avisado(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")
    price_list = await _seeded_price_list(db_session, "BR", "lojista")
    base = (await db_session.execute(
        select(Product).where(Product.id == s.product_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    catalog = (await db_session.execute(
        select(Catalog).where(Catalog.id == base.catalog_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    other = await make_product(
        db_session, market_code="BR", product_code=f"CPS-{uuid.uuid4().hex[:6].upper()}",
        description="Produto simples", catalog=catalog,
    )
    other.type = base.type
    await make_product_market(db_session, other)
    await make_product_price(db_session, other, price_list, amount=Decimal("80.00"))
    await db_session.commit()

    created = await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": [
            _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe)),
            {"product_code": other.product_code, "qty": 1},
        ]},
        headers=_auth(s.token),
    )
    assert created.status_code == 201, created.text
    source = created.json()
    inactive_line = next(i for i in source["items"] if i["product_code"] == s.product_code)
    other_line = next(i for i in source["items"] if i["product_code"] == other.product_code)

    await db_session.execute(
        update(Product).where(Product.id == s.product_id).values(is_active=False)
    )
    await db_session.commit()
    db_session.expunge_all()

    response = await _post_copy(client, s, source, [
        _from_source(s, inactive_line, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe)),
        {"product_code": other.product_code, "qty": 1, "source_order_item_id": other_line["id"]},
    ])
    assert response.status_code == 201, response.text
    body = response.json()
    assert [i["product_code"] for i in body["items"]] == [other.product_code]
    assert [row["product_code"] for row in body["copy_skipped"]] == [s.product_code]
    assert "inativo" in body["copy_skipped"][0]["reason"]


async def test_item_novo_na_tela_nao_ganha_a_tolerancia_da_copia(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A referência à origem não vira passe livre: item sem vínculo, ou trocado
    por outro produto, segue a criação normal e falha (404) em vez de ser pulado."""
    s = await _scenario(db_session, "BR")
    source = await _source(client, s)
    line = source["items"][0]

    sem_vinculo = await _post_copy(client, s, source, [
        {"product_code": "NAO-EXISTE", "qty": 1},
    ])
    assert sem_vinculo.status_code == 404, sem_vinculo.text

    trocado = await _post_copy(client, s, source, [
        {"product_code": "NAO-EXISTE", "qty": 1, "source_order_item_id": line["id"]},
    ])
    assert trocado.status_code == 404, trocado.text


async def test_copy_source_de_outro_mercado_ou_inexistente_devolve_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_br = await _scenario(db_session, "BR")
    s_eu = await _scenario(db_session, "EU")
    source = await _source(client, s_br)

    cross = await _post_copy(client, s_eu, source, [_item(s_eu, qty=1)])
    assert cross.status_code == 404, cross.text
    missing = await _post_copy(client, s_br, {"id": str(uuid.uuid4())}, [_item(s_br, qty=1)])
    assert missing.status_code == 404, missing.text


async def test_especial_copiado_mantem_codigo_percentual_e_comentario(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "EU")
    created = await _post_order(client, s, [
        {"product_code": s.product_code, "qty": 1, "is_special": True,
         "special_percent": "10", "comment": "Tampo sob medida"},
    ])
    assert created.status_code == 201, created.text
    source = created.json()
    [special] = source["items"]

    copied = await _post_copy(client, s, source, [{
        "product_code": s.product_code, "qty": 1, "is_special": True,
        "special_code": special["special_code"], "special_percent": "10",
        "comment": special["comment"], "source_order_item_id": special["id"],
    }])
    assert copied.status_code == 201, copied.text
    [item] = copied.json()["items"]
    assert item["is_special"] is True
    assert item["special_code"] == special["special_code"]
    assert Decimal(item["special_percent"]) == Decimal("10")
    assert item["comment"] == "Tampo sob medida"

    # Especial NOVO na tela, sem comentário, segue sendo recusado (422).
    novo = await _post_copy(client, s, source, [
        {"product_code": s.product_code, "qty": 1, "is_special": True, "special_percent": "5"},
    ])
    assert novo.status_code == 422, novo.text
