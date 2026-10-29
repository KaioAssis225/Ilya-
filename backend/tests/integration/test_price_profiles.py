"""P07 — perfis de preço, arredondamento e tributo BRL/IPI × EUR/IVA (HTTP + PostgreSQL).

Oráculo independente: os valores esperados abaixo são LITERAIS, calculados à
mão a partir do contrato comercial/fiscal e anotados ao lado de cada caso. O
teste nunca chama `_calculate_order_line`, `_money` ou qualquer helper de
orders.py para obter o esperado.

Contrato (regra, não saída):
* preço unitário = valor do SKU na lista de preço do perfil do cliente
  (lojista/corporativo/pvp/arquiteto); `price_list_code` diferente do perfil
  é 422 para qualquer papel, exceto a tabela já gravada no pedido em edição;
  sem preço na lista → 422, sem fallback para outra lista;
* linha: subtotal = ROUND_HALF_UP_2(qty × unit × (100 − desconto%) / 100),
  arredondado uma vez por linha, depois da multiplicação pela quantidade;
* tributo da linha = ROUND_HALF_UP_2(subtotal × alíquota / 100);
  total_ipi = soma dos tributos de linha já arredondados;
* BR: alíquota = IPI do grupo fiscal do tipo; rótulo "IPI"; moeda BRL;
* EU: alíquota = IVA aprovado nominalmente no SKU (`VAT_APPROVED`); rótulo
  "IVA"; moeda EUR. IVA pendente/rejeitado → 422 (ISO-24), sem fallback para
  IPI do grupo, tabela por tipo (`market_tax_rates`), SKU BR homônimo ou zero.
  Zero só vale quando é a taxa aprovada explicitamente;
* Arquiteto/PVP existem somente no EU: cliente BR não pode receber o perfil.

Rejeições conferem o banco depois de reproduzir o rollback de `get_db`
(ver docstring de test_optional_applications_flow.py sobre o harness).

Dados 100% sintéticos.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.client import Client
from app.models.market import (
    MarketTaxRate,
    PriceList,
    ProductMarket,
    VAT_APPROVED,
    VAT_PENDING,
    VAT_REJECTED,
)
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import UserRole
from app.models.catalog import Catalog
from tests.factories import (
    make_catalog,
    make_client,
    make_product,
    make_product_group,
    make_product_market,
    make_product_price,
    make_product_type,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP_SCOPE = {"skip_market_scope": True}
D = Decimal


# ── Builders locais ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Admin:
    token: str
    user_id: uuid.UUID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _admin(db: AsyncSession, market: str) -> Admin:
    user = await make_user(
        db, email=f"p07-price-{market.lower()}-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.admin, home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    return Admin(create_access_token(user.id, "admin", user.auth_version, market), user.id)


async def _price_list(db: AsyncSession, market: str, code: str) -> PriceList:
    return (await db.execute(
        select(PriceList).where(PriceList.market_code == market, PriceList.code == code)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()


async def _product(
    db: AsyncSession,
    market: str,
    approver_id: uuid.UUID,
    *,
    amounts: dict[str, Decimal],
    tax_rate: Decimal | None,
    vat_status: str = VAT_APPROVED,
    product_code: str | None = None,
    catalog: Catalog | None = None,
) -> tuple[str, str]:
    """Cria SKU com tipo/grupo fiscal e preço por lista. Devolve (código, tipo).

    BR: `tax_rate` vira o IPI do grupo. EU: grupo fica com IPI 0 (constraint) e
    `tax_rate` vira o IVA do SKU no status pedido.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    group = await make_product_group(
        db, market_code=market, name=f"P07 preço grupo {suffix}",
        ipi=tax_rate if market == "BR" and tax_rate is not None else D("0"),
    )
    product_type = await make_product_type(
        db, market_code=market, name=f"P07 preço tipo {suffix}", group=group,
    )
    product = await make_product(
        db, market_code=market, product_code=product_code or f"P07P-{market}-{suffix}",
        description="Mesa sintética P07",
        catalog=catalog,
    )
    product.type = product_type.name
    product_market = await make_product_market(db, product)
    if market == "EU":
        product_market.vat_rate = tax_rate
        product_market.vat_status = vat_status
        if vat_status == VAT_APPROVED:
            product_market.approved_by_user_id = approver_id
            product_market.approved_at = datetime.now(timezone.utc)
    for list_code, amount in amounts.items():
        await make_product_price(db, product, await _price_list(db, market, list_code), amount=amount)
    await db.flush()
    return product.product_code, product_type.name


async def _client(db: AsyncSession, market: str, profile: str) -> uuid.UUID:
    client = await make_client(
        db, await _price_list(db, market, profile),
        market_code=market, name=f"P07 cliente {profile} {uuid.uuid4().hex[:6]}",
    )
    client.price_profile = profile
    await db.flush()
    return client.id


async def _post_order(
    client: AsyncClient,
    admin: Admin,
    client_id: uuid.UUID,
    items: list[dict],
    *,
    price_list_code: str | None = None,
):
    payload = {"client_id": str(client_id), "items": items}
    if price_list_code is not None:
        payload["price_list_code"] = price_list_code
    return await client.post(
        "/api/v1/orders",
        json=payload,
        headers=_auth(admin.token),
    )


async def _discard_failed_request(db: AsyncSession) -> None:
    """Emula o rollback de `get_db` após exceção e descarta o identity map."""
    await db.rollback()
    db.expunge_all()


async def _order_count(db: AsyncSession, client_id: uuid.UUID) -> int:
    return (await db.execute(
        select(func.count()).select_from(Order).where(Order.client_id == client_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


# ── Perfis BR: BRL/IPI ─────────────────────────────────────────────────────────
# Listas: lojista 1000.00, corporativo 850.00. IPI 9.75%. qty 3, desconto 7.50%.
#   lojista:     1000.00 × 92.5/100 = 925.00;  × 3 = 2775.00
#                2775.00 × 9.75/100 = 270.5625 → 270.56;   total 3045.56
#   corporativo:  850.00 × 92.5/100 = 786.25;  × 3 = 2358.75
#                2358.75 × 9.75/100 = 229.978125 → 229.98; total 2588.73
_BR_AMOUNTS = {"lojista": D("1000.00"), "corporativo": D("850.00")}
_BR_CASES = [
    ("lojista", D("1000.00"), D("2775.00"), D("270.56"), D("3045.56")),
    ("corporativo", D("850.00"), D("2358.75"), D("229.98"), D("2588.73")),
]

# ── Perfis EU: EUR/IVA aprovado ────────────────────────────────────────────────
# Listas: lojista 1000.00, corporativo 850.00, pvp 1200.00, arquiteto 700.00.
# IVA aprovado 23.00%. qty 3, desconto 7.50%.
#   lojista:     2775.00 × 23/100 = 638.25;               total 3413.25
#   corporativo: 2358.75 × 23/100 = 542.5125 → 542.51;    total 2901.26
#   pvp:         1200.00 × 0.925 = 1110.00; × 3 = 3330.00
#                3330.00 × 23/100 = 765.90;               total 4095.90
#   arquiteto:    700.00 × 0.925 = 647.50;  × 3 = 1942.50
#                1942.50 × 23/100 = 446.775 → 446.78;     total 2389.28
_EU_AMOUNTS = {
    "lojista": D("1000.00"), "corporativo": D("850.00"),
    "pvp": D("1200.00"), "arquiteto": D("700.00"),
}
_EU_CASES = [
    ("lojista", D("1000.00"), D("2775.00"), D("638.25"), D("3413.25")),
    ("corporativo", D("850.00"), D("2358.75"), D("542.51"), D("2901.26")),
    ("pvp", D("1200.00"), D("3330.00"), D("765.90"), D("4095.90")),
    ("arquiteto", D("700.00"), D("1942.50"), D("446.78"), D("2389.28")),
]


@pytest.mark.parametrize(
    ("market", "rate", "label", "currency", "profile", "unit", "subtotal", "tax", "total"),
    [("BR", D("9.75"), "IPI", "BRL", *case) for case in _BR_CASES]
    + [("EU", D("23.00"), "IVA", "EUR", *case) for case in _EU_CASES],
    ids=[f"BR-{case[0]}" for case in _BR_CASES] + [f"EU-{case[0]}" for case in _EU_CASES],
)
async def test_reg_price_profile_selects_list_and_tax_with_half_up_rounding(
    client: AsyncClient,
    db_session: AsyncSession,
    market: str,
    rate: Decimal,
    label: str,
    currency: str,
    profile: str,
    unit: Decimal,
    subtotal: Decimal,
    tax: Decimal,
    total: Decimal,
) -> None:
    admin = await _admin(db_session, market)
    amounts = _BR_AMOUNTS if market == "BR" else _EU_AMOUNTS
    code, _ = await _product(db_session, market, admin.user_id, amounts=amounts, tax_rate=rate)
    client_id = await _client(db_session, market, profile)

    response = await _post_order(client, admin, client_id, [
        {"product_code": code, "qty": 3, "discount": "7.50"},
    ])
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["price_list_code"] == profile
    assert body["currency"] == currency
    assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
        subtotal, tax, total,
    )
    [item] = body["items"]
    assert _dec(item["unit_price"]) == unit
    assert _dec(item["discount"]) == D("7.50")
    assert _dec(item["ipi_rate"]) == rate
    assert _dec(item["ipi_value"]) == tax
    assert item["tax_label"] == label
    assert item["currency"] == currency

    order = (await db_session.execute(
        select(Order).where(Order.id == uuid.UUID(body["id"])).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    assert (order.total_value, order.total_ipi, order.total_with_ipi) == (subtotal, tax, total)
    assert order.price_list_code == profile


# ── Arredondamento ─────────────────────────────────────────────────────────────
# Casos escolhidos para separar HALF_UP de HALF_EVEN/truncamento e para fixar o
# ponto do arredondamento (linha × unidade; linha × total).
@pytest.mark.parametrize(
    ("market", "amount", "rate", "qty", "discount", "subtotal", "tax", "total"),
    [
        # 0.25 × 50/100 = 0.125 → HALF_UP 0.13 (HALF_EVEN/truncar dariam 0.12)
        ("BR", D("0.25"), D("0.00"), 1, "50.00", D("0.13"), D("0.00"), D("0.13")),
        # 3 × 0.125 = 0.375 → 0.38 (arredondar o unitário antes daria 3 × 0.13 = 0.39)
        ("BR", D("0.25"), D("0.00"), 3, "50.00", D("0.38"), D("0.00"), D("0.38")),
        # IPI: 100.10 × 5/100 = 5.005 → HALF_UP 5.01 (HALF_EVEN daria 5.00)
        ("BR", D("100.10"), D("5.00"), 1, "0", D("100.10"), D("5.01"), D("105.11")),
        # IVA: 0.50 × 13/100 = 0.065 → HALF_UP 0.07 (HALF_EVEN daria 0.06)
        ("EU", D("0.50"), D("13.00"), 1, "0", D("0.50"), D("0.07"), D("0.57")),
    ],
    ids=["br-linha-half-up", "br-arredonda-apos-qtd", "br-ipi-half-up", "eu-iva-half-up"],
)
async def test_reg_price_rounding_is_half_up_per_line(
    client: AsyncClient,
    db_session: AsyncSession,
    market: str,
    amount: Decimal,
    rate: Decimal,
    qty: int,
    discount: str,
    subtotal: Decimal,
    tax: Decimal,
    total: Decimal,
) -> None:
    admin = await _admin(db_session, market)
    code, _ = await _product(
        db_session, market, admin.user_id, amounts={"lojista": amount}, tax_rate=rate,
    )
    client_id = await _client(db_session, market, "lojista")

    response = await _post_order(client, admin, client_id, [
        {"product_code": code, "qty": qty, "discount": discount},
    ])
    assert response.status_code == 201, response.text
    body = response.json()
    assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
        subtotal, tax, total,
    )


async def test_reg_price_order_tax_is_sum_of_rounded_line_taxes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Duas linhas de 0.10 a 5%: 0.005 → 0.01 em cada linha; total_ipi 0.02.

    Tributar o total (0.20 × 5% = 0.01) daria outro valor — o contrato é por linha.
    """
    admin = await _admin(db_session, "BR")
    # Mesmo catálogo: um pedido não mistura catálogos (catalog_permissions_r21).
    catalog = await make_catalog(db_session, market_code="BR")
    code_a, _ = await _product(
        db_session, "BR", admin.user_id, amounts={"lojista": D("0.10")}, tax_rate=D("5.00"),
        catalog=catalog,
    )
    code_b, _ = await _product(
        db_session, "BR", admin.user_id, amounts={"lojista": D("0.10")}, tax_rate=D("5.00"),
        catalog=catalog,
    )
    client_id = await _client(db_session, "BR", "lojista")

    response = await _post_order(client, admin, client_id, [
        {"product_code": code_a, "qty": 1}, {"product_code": code_b, "qty": 1},
    ])
    assert response.status_code == 201, response.text
    body = response.json()
    assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
        D("0.20"), D("0.02"), D("0.22"),
    )
    assert sorted(_dec(item["ipi_value"]) for item in body["items"]) == [D("0.01"), D("0.01")]


# ── Perfil sem preço / perfil indevido ─────────────────────────────────────────

async def test_reg_price_missing_price_in_profile_list_is_422_without_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cliente Arquiteto, SKU só com preço Lojista → 422; nunca usa a lista Lojista."""
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts={"lojista": D("1000.00")}, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "arquiteto")
    await db_session.commit()

    response = await _post_order(client, admin, client_id, [{"product_code": code, "qty": 1}])
    assert response.status_code == 422, response.text
    assert "Arquiteto" in response.json()["detail"]
    await _discard_failed_request(db_session)
    assert await _order_count(db_session, client_id) == 0


@pytest.mark.parametrize("profile", ["arquiteto", "pvp"])
async def test_reg_price_br_client_cannot_receive_eu_only_profile(
    client: AsyncClient, db_session: AsyncSession, profile: str
) -> None:
    admin = await _admin(db_session, "BR")
    client_id = await _client(db_session, "BR", "lojista")
    original_list_id = (await _price_list(db_session, "BR", "lojista")).id
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/clients/{client_id}",
        json={"price_profile": profile},
        headers=_auth(admin.token),
    )
    assert response.status_code == 422, response.text

    await _discard_failed_request(db_session)
    row = (await db_session.execute(
        select(Client.price_profile, Client.price_list_id).where(Client.id == client_id)
        .execution_options(**_SKIP_SCOPE)
    )).one()
    assert (row.price_profile, row.price_list_id) == ("lojista", original_list_id)


async def test_reg_price_eu_client_switched_to_architect_is_billed_by_architect_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Seleção de Arquiteto EU pela API → pedido usa a lista Arquiteto.

    700.00 × 1 = 700.00; IVA 23% = 161.00; total 861.00.
    """
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts=_EU_AMOUNTS, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "lojista")
    architect_list_id = (await _price_list(db_session, "EU", "arquiteto")).id
    await db_session.commit()

    patch = await client.patch(
        f"/api/v1/clients/{client_id}",
        json={"price_profile": "arquiteto"},
        headers=_auth(admin.token),
    )
    assert patch.status_code == 200, patch.text
    row = (await db_session.execute(
        select(Client.price_profile, Client.price_list_id).where(Client.id == client_id)
        .execution_options(**_SKIP_SCOPE)
    )).one()
    assert (row.price_profile, row.price_list_id) == ("arquiteto", architect_list_id)

    response = await _post_order(client, admin, client_id, [{"product_code": code, "qty": 1}])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["price_list_code"] == "arquiteto"
    assert _dec(body["items"][0]["unit_price"]) == D("700.00")
    assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
        D("700.00"), D("161.00"), D("861.00"),
    )


@pytest.mark.parametrize("market", ["BR", "EU"])
@pytest.mark.parametrize("requested", ["corporativo", "pvp", "arquiteto"])
async def test_reg_price_quote_rejects_list_other_than_client_billing(
    client: AsyncClient, db_session: AsyncSession, market: str, requested: str
) -> None:
    """Cliente Lojista fecha só em Lojista, inclusive para admin: outra tabela
    em `price_list_code` é 422 e nenhum pedido é gravado."""
    admin = await _admin(db_session, market)
    amounts = _BR_AMOUNTS if market == "BR" else _EU_AMOUNTS
    code, _ = await _product(db_session, market, admin.user_id, amounts=amounts, tax_rate=D("23.00"))
    client_id = await _client(db_session, market, "lojista")
    await db_session.commit()

    rejected = await _post_order(
        client, admin, client_id, [{"product_code": code, "qty": 1}], price_list_code=requested,
    )
    assert rejected.status_code == 422, rejected.text
    assert "lojista" in rejected.json()["detail"]
    await _discard_failed_request(db_session)
    assert await _order_count(db_session, client_id) == 0

    own = await _post_order(
        client, admin, client_id, [{"product_code": code, "qty": 1}], price_list_code="lojista",
    )
    assert own.status_code == 201, own.text
    assert own.json()["price_list_code"] == "lojista"
    assert _dec(own.json()["items"][0]["unit_price"]) == D("1000.00")


async def test_reg_price_eu_quote_uses_client_billing_list_and_its_discount_cap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cliente Arquiteto: o pedido usa o preço e o teto Arquiteto (35%).

    700.00 × 65% = 455.00; IVA 23% = 104.65; total 559.65.
    """
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts=_EU_AMOUNTS, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "arquiteto")

    response = await _post_order(
        client,
        admin,
        client_id,
        [{"product_code": code, "qty": 1, "discount": "35.00"}],
        price_list_code="arquiteto",
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["price_list_code"] == "arquiteto"
    [item] = body["items"]
    assert _dec(item["unit_price"]) == D("700.00")
    assert _dec(item["discount"]) == D("35.00")
    assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
        D("455.00"), D("104.65"), D("559.65"),
    )

    above_cap = await _post_order(
        client,
        admin,
        client_id,
        [{"product_code": code, "qty": 1, "discount": "35.01"}],
        price_list_code="arquiteto",
    )
    assert above_cap.status_code == 422, above_cap.text
    assert "35" in above_cap.json()["detail"]


async def test_reg_price_eu_quote_edit_cannot_switch_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts=_EU_AMOUNTS, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "lojista")
    created = await _post_order(
        client,
        admin,
        client_id,
        [{"product_code": code, "qty": 1}],
        price_list_code="lojista",
    )
    assert created.status_code == 201, created.text
    order_id = uuid.UUID(created.json()["id"])

    updated = await client.put(
        f"/api/v1/orders/{order_id}",
        json={
            "price_list_code": "corporativo",
            "items": [{"product_code": code, "qty": 1, "discount": "25.00"}],
        },
        headers=_auth(admin.token),
    )
    assert updated.status_code == 422, updated.text
    await _discard_failed_request(db_session)
    stored = (await db_session.execute(
        select(Order.price_list_code, Order.total_value).where(Order.id == order_id)
        .execution_options(**_SKIP_SCOPE)
    )).one()
    assert (stored.price_list_code, stored.total_value) == ("lojista", D("1000.00"))


async def test_reg_price_eu_legacy_order_keeps_original_list_on_edit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pedido feito em PVP antes de o cliente passar a Lojista continua
    editável em PVP; só não pode ir para uma terceira tabela.

    1200.00 × 2 = 2400.00; IVA 23% = 552.00; total 2952.00.
    """
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts=_EU_AMOUNTS, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "pvp")
    await db_session.commit()
    created = await _post_order(client, admin, client_id, [{"product_code": code, "qty": 1}])
    assert created.status_code == 201, created.text
    assert created.json()["price_list_code"] == "pvp"
    order_id = created.json()["id"]

    patch = await client.patch(
        f"/api/v1/clients/{client_id}",
        json={"price_profile": "lojista"},
        headers=_auth(admin.token),
    )
    assert patch.status_code == 200, patch.text

    for sent in ({}, {"price_list_code": "pvp"}):
        updated = await client.put(
            f"/api/v1/orders/{order_id}",
            json={**sent, "items": [{"product_code": code, "qty": 2}]},
            headers=_auth(admin.token),
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["price_list_code"] == "pvp"
        assert _dec(body["items"][0]["unit_price"]) == D("1200.00")
        assert (_dec(body["total_value"]), _dec(body["total_ipi"]), _dec(body["total_with_ipi"])) == (
            D("2400.00"), D("552.00"), D("2952.00"),
        )

    third = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"price_list_code": "corporativo", "items": [{"product_code": code, "qty": 2}]},
        headers=_auth(admin.token),
    )
    assert third.status_code == 422, third.text


# ── ISO-24: IVA pendente/rejeitado ─────────────────────────────────────────────

@pytest.mark.parametrize(
    ("vat_status", "vat_rate"),
    [
        (VAT_PENDING, D("23.00")),
        (VAT_PENDING, None),
        (VAT_REJECTED, D("23.00")),
        (VAT_REJECTED, None),
    ],
    ids=["pendente-com-taxa", "pendente-sem-taxa", "rejeitado-com-taxa", "rejeitado-sem-taxa"],
)
async def test_iso24_unapproved_vat_is_422_without_any_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
    vat_status: str,
    vat_rate: Decimal | None,
) -> None:
    """Todas as fontes alternativas existem e nenhuma pode ser usada:
    SKU BR homônimo com IPI 10%, tabela EU por tipo com 23% e grupo EU com 0%."""
    admin = await _admin(db_session, "EU")
    br_admin = await _admin(db_session, "BR")
    code, type_name = await _product(
        db_session, "EU", admin.user_id,
        amounts={"lojista": D("1000.00")}, tax_rate=vat_rate, vat_status=vat_status,
    )
    await _product(
        db_session, "BR", br_admin.user_id,
        amounts={"lojista": D("1000.00")}, tax_rate=D("10.00"), product_code=code,
    )
    db_session.add(MarketTaxRate(market_code="EU", product_type=type_name, rate=D("23.00")))
    client_id = await _client(db_session, "EU", "lojista")
    await db_session.commit()

    response = await _post_order(client, admin, client_id, [{"product_code": code, "qty": 1}])
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert code in detail and "IVA aprovado" in detail

    await _discard_failed_request(db_session)
    assert await _order_count(db_session, client_id) == 0


async def test_iso24_mixed_order_with_one_pending_vat_saves_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _admin(db_session, "EU")
    approved, _ = await _product(
        db_session, "EU", admin.user_id, amounts={"lojista": D("100.00")}, tax_rate=D("23.00"),
    )
    pending, _ = await _product(
        db_session, "EU", admin.user_id, amounts={"lojista": D("100.00")},
        tax_rate=D("23.00"), vat_status=VAT_PENDING,
    )
    client_id = await _client(db_session, "EU", "lojista")
    await db_session.commit()

    response = await _post_order(client, admin, client_id, [
        {"product_code": approved, "qty": 1}, {"product_code": pending, "qty": 1},
    ])
    assert response.status_code == 422, response.text
    assert pending in response.json()["detail"]

    await _discard_failed_request(db_session)
    assert await _order_count(db_session, client_id) == 0


async def test_iso24_explicitly_approved_zero_vat_is_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zero aprovado por pessoa é cadastro, não fallback: 100.00 × 0% = 0.00."""
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts={"lojista": D("100.00")}, tax_rate=D("0.00"),
    )
    client_id = await _client(db_session, "EU", "lojista")

    response = await _post_order(client, admin, client_id, [{"product_code": code, "qty": 1}])
    assert response.status_code == 201, response.text
    [item] = response.json()["items"]
    assert (_dec(item["ipi_rate"]), _dec(item["ipi_value"]), item["tax_label"]) == (
        D("0.00"), D("0.00"), "IVA",
    )


async def test_iso24_recalculation_after_vat_revoked_is_422_and_keeps_snapshot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pedido EU criado com IVA aprovado; IVA volta a pendente; PUT recalcula → 422.

    Snapshot original: 1000.00 × 0.925 × 3 = 2775.00; IVA 23% = 638.25; 3413.25.
    """
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts={"lojista": D("1000.00")}, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "lojista")
    item_payload = {"product_code": code, "qty": 3, "discount": "7.50"}

    created = await _post_order(client, admin, client_id, [item_payload])
    assert created.status_code == 201, created.text
    order_id = uuid.UUID(created.json()["id"])
    original_version = created.json()["document_version"]

    product_market = (await db_session.execute(
        select(ProductMarket)
        .join(Product, Product.id == ProductMarket.product_id)
        .where(
            Product.product_code == code,
            Product.market_code == "EU",
            ProductMarket.market_code == "EU",
        )
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    product_market.vat_status = VAT_PENDING
    product_market.approved_by_user_id = None
    product_market.approved_at = None
    await db_session.commit()

    response = await client.put(
        f"/api/v1/orders/{order_id}",
        json={"items": [item_payload]},
        headers=_auth(admin.token),
    )
    assert response.status_code == 422, response.text
    assert "IVA aprovado" in response.json()["detail"]

    await _discard_failed_request(db_session)
    order = (await db_session.execute(
        select(Order).where(Order.id == order_id).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    assert (order.total_value, order.total_ipi, order.total_with_ipi) == (
        D("2775.00"), D("638.25"), D("3413.25"),
    )
    assert order.document_version == original_version
    items = (await db_session.execute(
        select(OrderItem.ipi_rate, OrderItem.ipi_value, OrderItem.tax_label)
        .where(OrderItem.order_id == order_id)
        .execution_options(**_SKIP_SCOPE)
    )).all()
    assert [(row.ipi_rate, row.ipi_value, row.tax_label) for row in items] == [
        (D("23.00"), D("638.25"), "IVA"),
    ]


async def test_reg_price_eu_quote_client_account_cannot_pick_hidden_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Conta de cliente Lojista não fatura em PVP só por mandar `price_list_code`."""
    admin = await _admin(db_session, "EU")
    code, _ = await _product(
        db_session, "EU", admin.user_id, amounts=_EU_AMOUNTS, tax_rate=D("23.00"),
    )
    client_id = await _client(db_session, "EU", "lojista")
    account = await make_user(
        db_session,
        email=f"p07-price-account-{uuid.uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.cliente, home_market="EU",
    )
    account.linked_id = client_id
    await make_user_market(
        db_session, account, market_code="EU", role="cliente", linked_client_id=client_id,
    )
    await db_session.commit()
    token = Admin(
        create_access_token(account.id, "cliente", account.auth_version, "EU"), account.id,
    )

    hidden = await _post_order(
        client, token, client_id, [{"product_code": code, "qty": 1}], price_list_code="pvp",
    )
    assert hidden.status_code == 422, hidden.text
    assert "pvp" in hidden.json()["detail"]
    await _discard_failed_request(db_session)
    assert await _order_count(db_session, client_id) == 0

    own = await _post_order(
        client, token, client_id, [{"product_code": code, "qty": 1}], price_list_code="lojista",
    )
    assert own.status_code == 201, own.text
    assert own.json()["price_list_code"] == "lojista"
