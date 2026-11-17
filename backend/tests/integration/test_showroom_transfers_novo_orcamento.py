"""Transferência para "Novo orçamento": a peça só sai do estoque ao salvar.

Contrato (PostgreSQL real, HTTP):

* a transferência NÃO cria orçamento: o destino "novo orçamento" não existe na
  rota de transferência (a tela leva a peça para a aba e o usuário salva);
* ao salvar o orçamento novo com ``showroom_source_item_id`` a quantidade da
  linha sai da box na mesma transação, e a transferência entra no histórico;
* saldo insuficiente na hora de salvar recusa com mensagem clara e não cria nada;
* orçamento já realizado (finalizado/em etapa) ou cancelado nunca recebe peça.

Dados 100% sintéticos.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import UserMarket
from app.models.order import Order
from app.models.product import Product
from tests.integration.test_optional_applications_flow import Scenario, _auth, _choice, _scenario
from tests.integration.test_showroom_boxes import BASE
from tests.integration.test_showroom_transfers import (
    allow_showrooms,
    make_box,
    quantities,
    stock,
    transfer_url,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def stocked_scenario(client: AsyncClient, db_session: AsyncSession, quantity: int = 4):
    """Cenário EU com a box 'Origem' contendo o produto com opcional + Customizado."""
    s = await _scenario(db_session, "EU", paint_brand="IBTW")
    await allow_showrooms(db_session, s)
    headers = _auth(s.token)
    box = await make_box(client, headers, "Origem")
    product = await db_session.get(Product, s.product_id)
    await stock(client, headers, box, product, quantity, choices=[
        {"application_id": str(s.app_feet), "optional_id": str(s.opt_black)},
        {"application_id": str(s.app_back), "custom": True},
    ])
    item = (await client.get(BASE, headers=headers)).json()[0]["items"][0]
    return s, headers, box, item


def order_payload(s: Scenario, item: dict, qty: int, **extra) -> dict:
    return {
        "client_id": str(s.client_id),
        "items": [{
            "product_code": s.product_code, "qty": qty,
            "showroom_source_item_id": item["item_id"],
            "optional_choices": [
                _choice(s.app_feet, s.opt_black),
                {"application_id": str(s.app_back), "custom_text": ""},
            ],
            **extra,
        }],
    }


async def test_novo_orcamento_nao_e_destino_da_transferencia(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session)

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 1,
        "destination": {"type": "new_order", "client_id": str(s.client_id)},
    }, headers=headers)

    assert response.status_code == 422
    assert await quantities(client, headers, box) == {s.product_code: 4}
    assert (await client.get("/api/v1/orders", headers=headers)).json() == []
    assert (await client.get(transfer_url(box), headers=headers)).json() == []


async def test_salvar_o_orcamento_novo_baixa_o_saldo_e_registra_a_transferencia(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session)

    created = await client.post("/api/v1/orders", json=order_payload(s, item, 3), headers=headers)

    assert created.status_code == 201, created.text
    order = created.json()
    [line] = order["items"]
    assert Decimal(str(line["qty"])) == 3
    # Preço, desconto e IVA resolvidos pelo servidor (100,00 x 3; IVA único no total).
    assert Decimal(line["unit_price"]) == Decimal("100.00") and Decimal(order["total_value"]) == Decimal("300.00")
    chosen = {row["application_id"]: row for row in line["optional_choices"]}
    assert chosen[str(s.app_feet)]["optional_id"] == str(s.opt_black)
    assert chosen[str(s.app_back)]["custom_text"] == ""
    assert await quantities(client, headers, box) == {s.product_code: 1}
    [record] = (await client.get(transfer_url(box), headers=headers)).json()
    assert (record["quantity"], record["destination_type"]) == (3, "order")
    assert record["destination_order_id"] == order["id"] and record["destination_order_code"] == order["code"]


async def test_salvar_com_a_quantidade_toda_esvazia_a_linha_da_box(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session, quantity=2)

    created = await client.post("/api/v1/orders", json=order_payload(s, item, 2), headers=headers)

    assert created.status_code == 201, created.text
    assert await quantities(client, headers, box) == {}


async def test_saldo_insuficiente_ao_salvar_recusa_e_nao_cria_orcamento(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session, quantity=2)
    # Outra pessoa consumiu parte do saldo depois que o item foi para a aba.
    other = await client.patch(
        f"{BASE}/{box['id']}/items/{item['item_id']}", json={"quantity": 1}, headers=headers,
    )
    assert other.status_code == 200, other.text

    response = await client.post("/api/v1/orders", json=order_payload(s, item, 2), headers=headers)

    assert response.status_code == 422
    assert "Saldo insuficiente" in response.json()["detail"] and "há 1" in response.json()["detail"]
    assert await quantities(client, headers, box) == {s.product_code: 1}
    assert (await client.get("/api/v1/orders", headers=headers)).json() == []
    assert (await client.get(transfer_url(box), headers=headers)).json() == []


async def test_linhas_do_mesmo_item_somam_e_peca_removida_e_recusada(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session, quantity=3)
    two_lines = order_payload(s, item, 2)
    two_lines["items"].append({**two_lines["items"][0], "qty": 2})

    over = await client.post("/api/v1/orders", json=two_lines, headers=headers)
    assert over.status_code == 422 and "pede 4 e há 3" in over.json()["detail"]

    removed = await client.delete(f"{BASE}/{box['id']}/items/{item['item_id']}", headers=headers)
    assert removed.status_code == 200
    gone = await client.post("/api/v1/orders", json=order_payload(s, item, 1), headers=headers)
    assert gone.status_code == 422 and "não está mais no estoque" in gone.json()["detail"]
    assert (await client.get("/api/v1/orders", headers=headers)).json() == []


async def test_baixa_exige_acesso_ao_estoque_e_so_vale_em_orcamento_novo(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session)
    created = await client.post("/api/v1/orders", json=order_payload(s, item, 1), headers=headers)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    edited = await client.put(
        f"/api/v1/orders/{order_id}", json={"items": order_payload(s, item, 1)["items"]}, headers=headers,
    )
    assert edited.status_code == 422 and "orçamento novo" in edited.json()["detail"]

    link = (await db_session.execute(select(UserMarket).where(
        UserMarket.user_id == s.user_id, UserMarket.market_code == "EU",
    ))).scalar_one()
    link.can_manage_showrooms = False
    await db_session.commit()
    denied = await client.post("/api/v1/orders", json=order_payload(s, item, 1), headers=headers)
    assert denied.status_code == 403
    link.can_manage_showrooms = True
    await db_session.commit()
    assert await quantities(client, headers, box) == {s.product_code: 3}


async def test_orcamento_ja_realizado_nunca_recebe_transferencia(
    client: AsyncClient, db_session: AsyncSession,
):
    s, headers, box, item = await stocked_scenario(client, db_session, quantity=2)
    created = await client.post("/api/v1/orders", json={
        "client_id": str(s.client_id),
        "items": [{"product_code": s.product_code, "qty": 1, "optional_choices": [_choice(s.app_feet, s.opt_taupe)]}],
    }, headers=headers)
    order_id = created.json()["id"]
    await db_session.execute(update(Order).where(Order.id == uuid.UUID(order_id)).values(
        is_finalized=True, order_stage="production", finalized_at=func.now(),
    ))
    await db_session.commit()

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 1,
        "destination": {"type": "order", "order_id": order_id},
    }, headers=headers)

    assert response.status_code == 409
    assert "já realizado" in response.json()["detail"]
    assert await quantities(client, headers, box) == {s.product_code: 2}
    assert (await client.get(transfer_url(box), headers=headers)).json() == []
    finalized = (await client.get(f"/api/v1/orders/{order_id}", headers=headers)).json()
    assert len(finalized["items"]) == 1
