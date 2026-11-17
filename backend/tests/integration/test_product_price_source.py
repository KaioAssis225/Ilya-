"""`product_prices` é a fonte do preço: gravação, leitura, ordenação e Moloni.

As colunas antigas de `products` (`price_lojista`, `price_corporativo`) ficam
deliberadamente DIFERENTES de `product_prices` nestes testes, para provar que
nada depende delas:

* `set_product_prices` insere, atualiza e ignora valor `None`;
* a listagem ordena e devolve o preço de `product_prices` (BR e EU);
* editar o preço pela API atualiza `product_prices`;
* o artigo novo no Moloni usa o preço de `product_prices`.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.product_prices import (
    get_list_price,
    load_price_lists,
    price_sort_expression,
    set_product_prices,
)
from app.core.security import create_access_token
from app.models.market import ProductPrice
from app.models.product import Product
from app.models.user import UserRole
from app.services.moloni_exporter import _article_price
from tests.factories import (
    make_product,
    make_product_market,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

D = Decimal


async def _admin_headers(db: AsyncSession, market: str) -> dict[str, str]:
    user = await make_user(
        db,
        email=f"preco-{market.lower()}-{uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.admin,
        home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    token = create_access_token(user.id, "admin", user.auth_version, market)
    return {"Authorization": f"Bearer {token}"}


async def _three_products(
    db: AsyncSession, market: str, tag: str
) -> list[Product]:
    """Três produtos cujo preço na COLUNA é o inverso do preço em `product_prices`."""
    lists = await load_price_lists(db, market)
    products = []
    for index, (column, table) in enumerate(
        [(D("300.00"), D("10.00")), (D("200.00"), D("20.00")), (D("100.00"), D("30.00"))]
    ):
        product = await make_product(
            db, market_code=market, product_code=f"{tag}-{index}",
            price=column, price_lojista=column,
        )
        await make_product_market(db, product)
        required = {"lojista": table, "corporativo": table + 1}
        if market == "EU":
            required.update({"pvp": table + 2, "arquiteto": table + 3})
        await set_product_prices(db, product.id, lists, required)
        products.append(product)
    await db.commit()
    return products


async def test_set_product_prices_insere_atualiza_e_ignora_none(
    db_session: AsyncSession,
) -> None:
    product = await make_product(db_session, market_code="BR")
    lists = await load_price_lists(db_session, "BR")

    written = await set_product_prices(
        db_session, product.id, lists, {"lojista": D("50.00"), "corporativo": None}
    )
    assert written == 1
    assert await get_list_price(db_session, product.id, "BR", "lojista") == D("50.00")
    assert await get_list_price(db_session, product.id, "BR", "corporativo") is None

    await set_product_prices(
        db_session, product.id, lists, {"lojista": D("60.00"), "corporativo": D("45.00")}
    )
    assert await get_list_price(db_session, product.id, "BR", "lojista") == D("60.00")
    assert await get_list_price(db_session, product.id, "BR", "corporativo") == D("45.00")
    rows = (await db_session.execute(
        select(ProductPrice).where(ProductPrice.product_id == product.id)
    )).scalars().all()
    assert len(rows) == 2, "atualizar não pode duplicar a linha"

    with pytest.raises(ValueError):
        await set_product_prices(db_session, product.id, lists, {"pvp": D("1.00")})


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_listagem_ordena_e_mostra_o_preco_de_product_prices(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    tag = f"PRC{uuid4().hex[:6].upper()}"
    headers = await _admin_headers(db_session, market)
    await _three_products(db_session, market, tag)

    for direction, expected in (("asc", ["-0", "-1", "-2"]), ("desc", ["-2", "-1", "-0"])):
        response = await client.get(
            "/api/v1/products",
            params={"q": tag, "sort_by": "price_lojista", "sort_dir": direction},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert [p["product_code"][len(tag):] for p in body] == expected
        # O que a tela mostra é o preço de `product_prices`, não o da coluna.
        by_code = {p["product_code"]: p for p in body}
        assert D(str(by_code[f"{tag}-0"]["price_lojista"])) == D("10.00")
        assert D(str(by_code[f"{tag}-2"]["price_lojista"])) == D("30.00")

    response = await client.get(
        "/api/v1/products",
        params={"q": tag, "sort_by": "price_corporativo", "sort_dir": "asc"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert [p["product_code"][len(tag):] for p in response.json()] == ["-0", "-1", "-2"]


async def test_editar_preco_pela_api_atualiza_product_prices(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tag = f"PRC{uuid4().hex[:6].upper()}"
    headers = await _admin_headers(db_session, "BR")
    products = await _three_products(db_session, "BR", tag)
    target_id = products[0].id

    response = await client.patch(
        f"/api/v1/products/{target_id}",
        json={"price_lojista": "77.00", "price_corporativo": "66.00"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert D(str(response.json()["price_lojista"])) == D("77.00")

    db_session.expire_all()
    assert await get_list_price(db_session, target_id, "BR", "lojista") == D("77.00")
    assert await get_list_price(db_session, target_id, "BR", "corporativo") == D("66.00")


async def test_preco_sem_linha_na_lista_conta_como_zero_na_ordenacao(
    db_session: AsyncSession,
) -> None:
    tag = f"PRC{uuid4().hex[:6].upper()}"
    lists = await load_price_lists(db_session, "BR")
    com_preco = await make_product(db_session, market_code="BR", product_code=f"{tag}-A")
    sem_preco = await make_product(db_session, market_code="BR", product_code=f"{tag}-B")
    await set_product_prices(db_session, com_preco.id, lists, {"lojista": D("5.00")})
    await db_session.commit()

    ordem = (await db_session.execute(
        select(Product.product_code)
        .where(Product.product_code.in_([com_preco.product_code, sem_preco.product_code]))
        .order_by(price_sort_expression("BR", "lojista"), Product.product_code)
    )).scalars().all()
    assert ordem == [sem_preco.product_code, com_preco.product_code]


async def test_artigo_do_moloni_usa_o_preco_de_product_prices(
    db_session: AsyncSession,
) -> None:
    lists = await load_price_lists(db_session, "EU")
    product = await make_product(
        db_session, market_code="EU", price=D("999.00"), price_lojista=D("999.00"),
    )
    await set_product_prices(db_session, product.id, lists, {"lojista": D("55.00")})
    await db_session.commit()

    assert await _article_price(db_session, product) == "55.00"


async def test_artigo_do_moloni_sem_linha_usa_a_coluna_antiga(
    db_session: AsyncSession,
) -> None:
    product = await make_product(
        db_session, market_code="EU", price=D("88.00"), price_lojista=D("88.00"),
    )
    await db_session.commit()

    assert await _article_price(db_session, product) == "88.00"
