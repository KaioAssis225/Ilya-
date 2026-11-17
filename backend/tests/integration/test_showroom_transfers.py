"""Transferência do Estoque EU: para outra box ou para um orçamento.

Contrato (PostgreSQL real, HTTP):

* a quantidade sai da origem e entra no destino na mesma transação; passar do
  saldo é 422 e nada muda;
* duas transferências simultâneas do mesmo item nunca deixam saldo negativo;
* para orçamento, a linha entra com o mesmo produto e os mesmos opcionais e o
  servidor resolve preço, desconto e IVA como num item normal;
* quem não administra o Estoque (ou está em outro mercado) não enxerga a área.

Dados 100% sintéticos.
"""
import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.market import Market, ProductMarket, ProductPrice, UserMarket
from app.models.product import Product
from app.models.showroom import ShowroomBox, ShowroomBoxItem, ShowroomTransfer
from app.models.user import User
from tests.factories import make_user_market
from tests.integration.conftest import _resolve_db_url
from tests.integration.test_optional_applications_flow import (
    Scenario,
    _auth,
    _choice,
    _scenario,
)
from tests.integration.test_showroom_boxes import BASE, auth, eu_price_list, person, priced_product

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def make_box(client: AsyncClient, headers: dict, name: str, price_list: str = "lojista") -> dict:
    response = await client.post(BASE, json={"name": name, "price_list_code": price_list}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def stock(client: AsyncClient, headers: dict, box: dict, product, quantity: int, choices=None) -> dict:
    response = await client.post(f"{BASE}/{box['id']}/items", json={
        "product_id": str(product.id), "quantity": quantity, "optional_choices": choices or [],
    }, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def transfer_url(box: dict) -> str:
    return f"{BASE}/{box['id']}/transfers"


async def quantities(client: AsyncClient, headers: dict, box: dict) -> dict[str, int]:
    rows = (await client.get(BASE, headers=headers)).json()
    current = next(row for row in rows if row["id"] == box["id"])
    return {row["product_code"]: row["quantity"] for row in current["items"]}


async def test_transferencia_parcial_e_total_entre_boxes(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await person(db_session, "partial", allowed=True)
    product = await priced_product(db_session)
    await db_session.commit()
    headers = auth(user, "vendedor")
    origem = await make_box(client, headers, "Origem")
    destino = await make_box(client, headers, "Destino")
    item = (await stock(client, headers, origem, product, 5))["items"][0]

    parcial = await client.post(transfer_url(origem), json={
        "item_id": item["item_id"], "quantity": 2,
        "destination": {"type": "box", "box_id": destino["id"]},
    }, headers=headers)
    assert parcial.status_code == 201, parcial.text
    assert parcial.json()["box"]["total_quantity"] == 3
    assert parcial.json()["transfer"]["quantity"] == 2
    assert await quantities(client, headers, origem) == {product.product_code: 3}
    assert await quantities(client, headers, destino) == {product.product_code: 2}

    total = await client.post(transfer_url(origem), json={
        "item_id": item["item_id"], "quantity": 3,
        "destination": {"type": "box", "box_id": destino["id"]},
    }, headers=headers)
    assert total.status_code == 201, total.text
    assert total.json()["box"]["items"] == []
    assert await quantities(client, headers, origem) == {}
    # Mesma configuração: soma na linha que já existia, sem duplicar.
    assert await quantities(client, headers, destino) == {product.product_code: 5}

    history = (await client.get(transfer_url(destino), headers=headers)).json()
    assert sorted((row["quantity"], row["source_box_name"], row["destination_box_name"]) for row in history) == [
        (2, "Origem", "Destino"), (3, "Origem", "Destino"),
    ]
    assert {row["created_by_name"] for row in history} == {user.full_name}


async def test_quantidade_maior_que_o_saldo_e_recusada_sem_mudar_nada(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await person(db_session, "overdraw", allowed=True)
    product = await priced_product(db_session)
    await db_session.commit()
    headers = auth(user, "vendedor")
    origem = await make_box(client, headers, "Origem")
    destino = await make_box(client, headers, "Destino")
    item = (await stock(client, headers, origem, product, 2))["items"][0]

    response = await client.post(transfer_url(origem), json={
        "item_id": item["item_id"], "quantity": 3,
        "destination": {"type": "box", "box_id": destino["id"]},
    }, headers=headers)

    assert response.status_code == 422
    assert "saldo" in response.json()["detail"]
    assert await quantities(client, headers, origem) == {product.product_code: 2}
    assert await quantities(client, headers, destino) == {}
    assert (await client.get(transfer_url(origem), headers=headers)).json() == []


async def test_destino_invalido_e_recusado(client: AsyncClient, db_session: AsyncSession):
    user = await person(db_session, "badtarget", allowed=True)
    product = await priced_product(db_session)
    await db_session.commit()
    headers = auth(user, "vendedor")
    origem = await make_box(client, headers, "Origem")
    # O produto só tem preço em lojista e pvp: arquiteto não tem.
    sem_preco = await make_box(client, headers, "Sem preço", price_list="arquiteto")
    item = (await stock(client, headers, origem, product, 2))["items"][0]

    def body(destination):
        return {"item_id": item["item_id"], "quantity": 1, "destination": destination}

    same = await client.post(transfer_url(origem), json=body({"type": "box", "box_id": origem["id"]}), headers=headers)
    missing = await client.post(transfer_url(origem), json=body({"type": "box", "box_id": str(uuid.uuid4())}), headers=headers)
    unpriced = await client.post(transfer_url(origem), json=body({"type": "box", "box_id": sem_preco["id"]}), headers=headers)
    other_item = await client.post(transfer_url(sem_preco), json=body({"type": "box", "box_id": origem["id"]}), headers=headers)

    assert [same.status_code, missing.status_code, unpriced.status_code, other_item.status_code] == [422, 404, 422, 404]
    assert await quantities(client, headers, origem) == {product.product_code: 2}


async def test_sem_acesso_nao_transfere(client: AsyncClient, db_session: AsyncSession):
    owner = await person(db_session, "owner", allowed=True)
    outsider = await person(db_session, "outsider", allowed=False)
    await make_user_market(db_session, owner, market_code="BR", role="vendedor")
    product = await priced_product(db_session)
    await db_session.commit()
    box = await make_box(client, auth(owner, "vendedor"), "Origem")
    other = await make_box(client, auth(owner, "vendedor"), "Destino")
    item = (await stock(client, auth(owner, "vendedor"), box, product, 2))["items"][0]
    payload = {
        "item_id": item["item_id"], "quantity": 1,
        "destination": {"type": "box", "box_id": other["id"]},
    }

    assert (await client.post(transfer_url(box), json=payload, headers=auth(outsider, "vendedor"))).status_code == 404
    assert (await client.get(transfer_url(box), headers=auth(outsider, "vendedor"))).status_code == 404
    assert (await client.post(transfer_url(box), json=payload, headers=auth(owner, "vendedor", "BR"))).status_code == 404
    assert (await client.post(transfer_url(box), json=payload)).status_code == 401
    assert await quantities(client, auth(owner, "vendedor"), box) == {product.product_code: 2}


async def allow_showrooms(db: AsyncSession, scenario: Scenario) -> None:
    link = (await db.execute(select(UserMarket).where(
        UserMarket.user_id == scenario.user_id, UserMarket.market_code == "EU",
    ))).scalar_one()
    link.can_manage_showrooms = True
    await db.commit()


async def test_transferencia_para_orcamento_novo_cria_a_linha_certa(
    client: AsyncClient, db_session: AsyncSession,
):
    s = await _scenario(db_session, "EU", paint_brand="IBTW")
    await allow_showrooms(db_session, s)
    headers = _auth(s.token)
    box = await make_box(client, headers, "Origem")
    product = await db_session.get(Product, s.product_id)
    # Escolha completa de uma aplicação e "Customizado" na outra.
    await stock(client, headers, box, product, 4, choices=[
        {"application_id": str(s.app_feet), "optional_id": str(s.opt_black)},
        {"application_id": str(s.app_back), "custom": True},
    ])
    item = (await client.get(BASE, headers=headers)).json()[0]["items"][0]

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 3,
        "destination": {"type": "new_order", "client_id": str(s.client_id)},
    }, headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["box"]["total_quantity"] == 1
    assert body["transfer"]["destination_type"] == "order"
    order = (await client.get(f"/api/v1/orders/{body['transfer']['destination_order_id']}", headers=headers)).json()
    assert order["is_finalized"] is False and order["code"] == body["transfer"]["destination_order_code"]
    [line] = order["items"]
    assert line["product_code"] == s.product_code
    assert Decimal(str(line["qty"])) == 3
    # Preço, desconto e IVA vêm do servidor: 100,00 x 3, sem desconto, IVA único no total.
    assert Decimal(line["unit_price"]) == Decimal("100.00") and Decimal(line["discount"]) == 0
    assert Decimal(order["total_value"]) == Decimal("300.00")
    assert Decimal(order["total_ipi"]) == Decimal("69.00")
    chosen = {row["application_id"]: row for row in line["optional_choices"]}
    assert chosen[str(s.app_feet)]["optional_id"] == str(s.opt_black)
    assert chosen[str(s.app_back)]["custom_text"] == "" and chosen[str(s.app_back)]["optional_id"] is None


async def test_transferencia_para_orcamento_existente_acrescenta_sem_perder_as_linhas(
    client: AsyncClient, db_session: AsyncSession,
):
    s = await _scenario(db_session, "EU")
    await allow_showrooms(db_session, s)
    headers = _auth(s.token)
    created = await client.post("/api/v1/orders", json={
        "client_id": str(s.client_id),
        "items": [{
            "product_code": s.product_code, "qty": 2,
            "optional_choices": [_choice(s.app_feet, s.opt_taupe)],
        }],
    }, headers=headers)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    box = await make_box(client, headers, "Origem")
    product = await db_session.get(Product, s.product_id)
    # Só um dos opcionais: opcional pendente é aceito no EU, como no orçamento.
    await stock(client, headers, box, product, 2, choices=[
        {"application_id": str(s.app_feet), "optional_id": str(s.opt_black)},
    ])
    item = (await client.get(BASE, headers=headers)).json()[0]["items"][0]

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 2,
        "destination": {"type": "order", "order_id": order_id},
    }, headers=headers)

    assert response.status_code == 201, response.text
    assert response.json()["box"]["items"] == []
    order = (await client.get(f"/api/v1/orders/{order_id}", headers=headers)).json()
    colors = sorted(
        (row["optional_choices"][0]["optional_id"], int(Decimal(str(row["qty"]))))
        for row in order["items"]
    )
    assert colors == sorted([(str(s.opt_taupe), 2), (str(s.opt_black), 2)])
    assert Decimal(order["total_value"]) == Decimal("400.00")
    history = (await client.get(transfer_url(box), headers=headers)).json()
    assert history[0]["destination_order_id"] == order_id


async def test_falha_ao_criar_o_orcamento_devolve_a_peca_ao_estoque(
    client: AsyncClient, db_session: AsyncSession,
):
    s = await _scenario(db_session, "EU")
    await allow_showrooms(db_session, s)
    headers = _auth(s.token)
    box = await make_box(client, headers, "Origem")
    product = await db_session.get(Product, s.product_id)
    await stock(client, headers, box, product, 2)
    item = (await client.get(BASE, headers=headers)).json()[0]["items"][0]

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 1,
        "destination": {"type": "new_order", "client_id": str(uuid.uuid4())},
    }, headers=headers)

    assert response.status_code == 404
    assert await quantities(client, headers, box) == {s.product_code: 2}
    assert (await client.get(transfer_url(box), headers=headers)).json() == []


async def test_orcamento_cancelado_nao_recebe_transferencia(
    client: AsyncClient, db_session: AsyncSession,
):
    s = await _scenario(db_session, "EU")
    await allow_showrooms(db_session, s)
    headers = _auth(s.token)
    created = await client.post("/api/v1/orders", json={
        "client_id": str(s.client_id),
        "items": [{
            "product_code": s.product_code, "qty": 1,
            "optional_choices": [_choice(s.app_feet, s.opt_taupe)],
        }],
    }, headers=headers)
    order_id = created.json()["id"]
    cancelled = await client.post(f"/api/v1/orders/{order_id}/cancel", json={}, headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    box = await make_box(client, headers, "Origem")
    product = await db_session.get(Product, s.product_id)
    await stock(client, headers, box, product, 1)
    item = (await client.get(BASE, headers=headers)).json()[0]["items"][0]

    response = await client.post(transfer_url(box), json={
        "item_id": item["item_id"], "quantity": 1,
        "destination": {"type": "order", "order_id": order_id},
    }, headers=headers)

    assert response.status_code == 409
    assert await quantities(client, headers, box) == {s.product_code: 1}


async def test_duas_transferencias_simultaneas_nao_deixam_saldo_negativo():
    """Dados confirmados no banco e duas requisições em conexões distintas.

    A fixture padrão usa uma só conexão, que serializaria tudo: aqui cada
    requisição abre a própria sessão, como em produção.
    """
    from app.api.deps import get_db_session
    from app.main import app
    from tests.factories.markets import require_market

    engine = create_async_engine(_resolve_db_url(), poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:8]
    boxes: list[uuid.UUID] = []
    ids: tuple = ()
    eu_was_enabled = None
    try:
        async with sessions() as setup:
            eu_was_enabled = (await setup.get(Market, "EU")).is_enabled
            await require_market(setup, "EU", enabled=True)
            await setup.commit()
            user = await person(setup, f"race{tag}", allowed=True)
            product = await priced_product(setup)
            origem = ShowroomBox(market_code="EU", name=f"Corrida origem {tag}", price_list_code="lojista")
            destino = ShowroomBox(market_code="EU", name=f"Corrida destino {tag}", price_list_code="lojista")
            setup.add_all([origem, destino])
            await setup.flush()
            item = ShowroomBoxItem(box_id=origem.id, product_id=product.id, quantity=5, configuration_key="base")
            setup.add(item)
            await setup.commit()
            headers = auth(user, "vendedor")
            boxes = [origem.id, destino.id]
            ids = (user.id, product.id, item.id, origem.id, destino.id)

        async def per_request_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db_session] = per_request_session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
            body = {
                "item_id": str(ids[2]), "quantity": 3,
                "destination": {"type": "box", "box_id": str(ids[4])},
            }
            results = await asyncio.gather(
                http.post(f"{BASE}/{ids[3]}/transfers", json=body, headers=headers),
                http.post(f"{BASE}/{ids[3]}/transfers", json=body, headers=headers),
            )
        statuses = sorted(response.status_code for response in results)
        async with sessions() as check:
            source_left = (await check.execute(
                select(ShowroomBoxItem.quantity).where(ShowroomBoxItem.id == ids[2])
            )).scalar_one_or_none()
            moved = (await check.execute(
                select(ShowroomBoxItem.quantity).where(ShowroomBoxItem.box_id == ids[4])
            )).scalar_one_or_none()
            recorded = len((await check.execute(
                select(ShowroomTransfer).where(ShowroomTransfer.source_box_id == ids[3])
            )).scalars().all())
        assert statuses == [201, 422]
        assert source_left == 2 and moved == 3 and recorded == 1
    finally:
        from app.api.deps import get_db_session as dependency
        from app.main import app as application

        application.dependency_overrides.pop(dependency, None)
        if eu_was_enabled is not None:
            async with sessions() as restore:
                (await restore.get(Market, "EU")).is_enabled = eu_was_enabled
                await restore.commit()
        if ids:
            async with sessions() as cleanup:
                await cleanup.execute(delete(ShowroomTransfer).where(ShowroomTransfer.source_box_id.in_(boxes)))
                await cleanup.execute(delete(ShowroomBox).where(ShowroomBox.id.in_(boxes)))
                await cleanup.execute(delete(ProductPrice).where(ProductPrice.product_id == ids[1]))
                await cleanup.execute(delete(ProductMarket).where(ProductMarket.product_id == ids[1]))
                await cleanup.execute(delete(Product).where(Product.id == ids[1]))
                await cleanup.execute(delete(UserMarket).where(UserMarket.user_id == ids[0]))
                await cleanup.execute(delete(User).where(User.id == ids[0]))
                await cleanup.commit()
        await engine.dispose()
