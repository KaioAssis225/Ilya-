"""TECIDO FORNECIDO — cadastro na ficha do produto e ponta a ponta (PostgreSQL real).

Simula o estado de produção: a categoria `TECIDOS_IBTW` já existe, o produto EU
tem a aplicação (ou o seletor antigo) dessa categoria e os dados do tecido
fornecido foram gravados. Confirma que a opção chega ao orçamento (catálogo),
mostra a metragem e muda o preço; e que o cadastro é só de admin/produtos.

Dados 100% sintéticos.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.supplied_fabric import SUPPLIED_FABRIC_CATEGORY
from app.models.market import ProductMarket, ProductSuppliedFabric, VAT_APPROVED
from app.models.optional_color import OptionalColor, product_optionals
from app.models.product import Product
from app.models.user import UserRole
from tests.factories import (
    make_product,
    make_product_market,
    make_product_price,
    make_user,
    make_user_market,
)
from tests.integration.test_supplied_fabric_flow import (
    Scenario,
    _auth,
    _both_supplied,
    _count_orders,
    _item,
    _post,
    _price_list,
    _scenario,
    _supplied,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP = {"skip_market_scope": True}
BODY = {
    "linear_meters": "13.20", "price_lojista": "700.10", "price_corporativo": "800.20",
    "price_pvp": "1400.30", "price_arquiteto": "900.40",
}


def _url(product_id: uuid.UUID) -> str:
    return f"/api/v1/products/{product_id}/supplied-fabric"


async def _user_headers(db: AsyncSession, role: UserRole, market: str = "EU") -> dict[str, str]:
    user = await make_user(db, email=f"tf-{role.value}-{uuid.uuid4().hex[:6]}@ilya-test.invalid", role=role, home_market=market)
    await make_user_market(db, user, market_code=market, role=role.value)
    token = create_access_token(user.id, role.value, user.auth_version, market)
    await db.commit()
    return _auth(token)


async def _product_id(db: AsyncSession, code: str) -> uuid.UUID:
    return (await db.execute(select(Product.id).where(Product.product_code == code).execution_options(**_SKIP))).scalar_one()


async def _legacy_product(db: AsyncSession, s: Scenario, *, with_data: bool) -> str:
    """Produto EU que usa o seletor antigo (opcional direto na categoria, sem aplicação)."""
    base = (await db.execute(select(Product).where(Product.id == s.id_with).execution_options(**_SKIP))).scalar_one()
    base_market = (await db.execute(select(ProductMarket).where(ProductMarket.product_id == s.id_with))).scalar_one()
    linen = (await db.execute(select(OptionalColor).where(OptionalColor.id == s.linen_id).execution_options(**_SKIP))).scalar_one()
    product = await make_product(db, market_code="EU", product_code=f"TFL-{uuid.uuid4().hex[:6].upper()}", description="Sofá antigo")
    product.type = base.type
    pm = await make_product_market(db, product)
    pm.vat_rate = Decimal("23.00")
    pm.vat_status = VAT_APPROVED
    pm.approved_by_user_id = base_market.approved_by_user_id
    pm.approved_at = datetime.now(timezone.utc)
    for code in ("lojista", "corporativo", "pvp", "arquiteto"):
        await make_product_price(db, product, await _price_list(db, "EU", code), amount=Decimal("1000.00"))
    await db.execute(product_optionals.insert().values(product_id=product.id, optional_id=linen.id))
    if with_data:
        db.add(ProductSuppliedFabric(
            product_id=product.id, linear_meters=Decimal("9.60"), price_lojista=Decimal("500.00"),
            price_corporativo=Decimal("550.00"), price_pvp=Decimal("1000.00"), price_arquiteto=Decimal("650.00"),
        ))
    await db.commit()
    return product.product_code


# ── Ponta a ponta: cadastro → catálogo → pedido ──────────────────────────────

async def test_admin_registers_data_then_option_reaches_catalog_and_changes_the_price(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    # Estado de produção: a aplicação TECIDOS_IBTW existe, mas ainda sem dado.
    other_id = await _product_id(db_session, s.code_without)
    before = await client.get("/api/v1/products", params={"limit": 50}, headers=_auth(s.token))
    assert {r["product_code"]: r["supplied_fabric"] for r in before.json()}[s.code_without] is None
    assert (await _post(client, s, [_item(s.code_without, _supplied(s.app_without))])).status_code == 422

    saved = await client.put(_url(other_id), json=BODY, headers=_auth(s.token))
    assert saved.status_code == 200, saved.text
    assert Decimal(str(saved.json()["linear_meters"])) == Decimal("13.20")

    after = await client.get("/api/v1/products", params={"limit": 50}, headers=_auth(s.token))
    fabric = {r["product_code"]: r["supplied_fabric"] for r in after.json()}[s.code_without]
    assert Decimal(str(fabric["linear_meters"])) == Decimal("13.20")
    assert {code: Decimal(str(v)) for code, v in fabric["prices"].items()} == {
        "lojista": Decimal("700.10"), "corporativo": Decimal("800.20"),
        "pvp": Decimal("1400.30"), "arquiteto": Decimal("900.40"),
    }
    order = await _post(client, s, [_item(s.code_without, _supplied(s.app_without))])
    assert order.status_code == 201, order.text
    item = order.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("700.10")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("13.20")


async def test_put_updates_existing_data_and_delete_removes_the_option(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    changed = await client.put(_url(s.id_with), json={**BODY, "price_lojista": "650.00", "linear_meters": "12"}, headers=_auth(s.token))
    assert changed.status_code == 200, changed.text
    order = await _post(client, s, [_item(s.code_with, *_both_supplied(s))])
    assert Decimal(str(order.json()["items"][0]["unit_price"])) == Decimal("650.00")
    assert Decimal(str(order.json()["items"][0]["supplied_fabric_meters"])) == Decimal("12.00")

    assert (await client.delete(_url(s.id_with), headers=_auth(s.token))).status_code == 204
    assert (await client.delete(_url(s.id_with), headers=_auth(s.token))).status_code == 204  # idempotente
    products = {r["product_code"]: r for r in (await client.get("/api/v1/products", params={"limit": 50}, headers=_auth(s.token))).json()}
    assert products[s.code_with]["supplied_fabric"] is None
    assert (await _post(client, s, [_item(s.code_with, *_both_supplied(s))])).status_code == 422


@pytest.mark.parametrize("override", [
    {"linear_meters": "0"}, {"linear_meters": "-1"}, {"linear_meters": "1.234"},
    {"price_pvp": "-0.01"}, {"price_lojista": "10.005"}, {"price_arquiteto": "abc"},
])
async def test_put_validates_meters_and_prices(client: AsyncClient, db_session: AsyncSession, override: dict) -> None:
    s = await _scenario(db_session)
    response = await client.put(_url(s.id_with), json={**BODY, **override}, headers=_auth(s.token))
    assert response.status_code == 422
    await db_session.rollback()
    db_session.expunge_all()
    assert (await db_session.get(ProductSuppliedFabric, s.id_with)).price_lojista == Decimal("700.10")  # nada mudou


async def test_put_requires_every_field(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    partial = {k: v for k, v in BODY.items() if k != "price_pvp"}
    assert (await client.put(_url(s.id_with), json=partial, headers=_auth(s.token))).status_code == 422


# ── RBAC e mercado ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [UserRole.vendedor, UserRole.cadastros, UserRole.executivo])
async def test_non_admin_cannot_register_or_remove(client: AsyncClient, db_session: AsyncSession, role: UserRole) -> None:
    s = await _scenario(db_session)
    other = await _user_headers(db_session, role)
    assert (await client.put(_url(s.id_with), json=BODY, headers=other)).status_code == 403
    assert (await client.delete(_url(s.id_with), headers=other)).status_code == 403
    assert (await db_session.get(ProductSuppliedFabric, s.id_with)) is not None


async def test_produtos_role_can_register(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    headers = await _user_headers(db_session, UserRole.produtos)
    assert (await client.put(_url(s.id_with), json=BODY, headers=headers)).status_code == 200


async def test_unauthenticated_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    assert (await client.put(_url(s.id_with), json=BODY)).status_code in (401, 403)


async def test_brazil_session_and_unknown_product_get_404(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    br = await _user_headers(db_session, UserRole.admin, "BR")
    assert (await client.put(_url(s.id_with), json=BODY, headers=br)).status_code == 404
    assert (await client.put(_url(uuid.uuid4()), json=BODY, headers=_auth(s.token))).status_code == 404
    await db_session.rollback()
    db_session.expunge_all()
    assert (await db_session.get(ProductSuppliedFabric, s.id_with)).price_lojista == Decimal("700.10")


# ── Seletor antigo (produto sem aplicação de tecido) ─────────────────────────

def _legacy_order(s: Scenario, code: str, value: str) -> dict:
    return {"client_id": str(s.client_id), "items": [{"product_code": code, "qty": 1, "opt_categories": {SUPPLIED_FABRIC_CATEGORY: value}}]}


async def test_legacy_selector_supplied_fabric_uses_sheet_price_and_meters(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    code = await _legacy_product(db_session, s, with_data=True)
    response = await client.post("/api/v1/orders", json=_legacy_order(s, code, "TECIDO FORNECIDO"), headers=_auth(s.token))
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("500.00")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("9.60")
    assert item["opt_categories"] == {SUPPLIED_FABRIC_CATEGORY: "TECIDO FORNECIDO"}
    # Com uma cor normal do cadastro o preço volta ao normal.
    normal = await client.post("/api/v1/orders", json=_legacy_order(s, code, "Linho"), headers=_auth(s.token))
    assert normal.status_code == 201, normal.text
    assert Decimal(str(normal.json()["items"][0]["unit_price"])) == Decimal("1000.00")
    assert normal.json()["items"][0]["supplied_fabric_meters"] is None


async def test_legacy_selector_without_data_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    code = await _legacy_product(db_session, s, with_data=False)
    response = await client.post("/api/v1/orders", json=_legacy_order(s, code, "TECIDO FORNECIDO"), headers=_auth(s.token))
    assert response.status_code == 422
    assert await _count_orders(db_session, s) == 0


# ── Aviso da importação: aplicação, seletor antigo ou nenhum dos dois ────────

async def test_import_warning_considers_application_legacy_selector_and_free_category(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    legacy_direct = await _legacy_product(db_session, s, with_data=False)       # product_optionals
    legacy_free = await _legacy_product(db_session, s, with_data=False)         # "permitir todos"
    free_id = await _product_id(db_session, legacy_free)
    await db_session.execute(product_optionals.delete().where(product_optionals.c.product_id == free_id))
    free = (await db_session.execute(select(Product).where(Product.id == free_id).execution_options(**_SKIP))).scalar_one()
    free.all_optionals_categories = f"OUTRA, {SUPPLIED_FABRIC_CATEGORY}"
    bare = await make_product(db_session, market_code="EU", product_code=f"TFB-{uuid.uuid4().hex[:6].upper()}", description="Sem tecido")
    await make_product_market(db_session, bare)
    other_category = await make_product(db_session, market_code="EU", product_code=f"TFC-{uuid.uuid4().hex[:6].upper()}", description="Outra categoria")
    other_category.all_optionals_categories = "OUTRA"
    await make_product_market(db_session, other_category)
    await db_session.commit()

    lines = [s.code_with, legacy_direct, legacy_free, bare.product_code, other_category.product_code]
    body = "COD;PVP;LOJISTA;ARQUITETO;CORPORATIVO;MTS TECIDO\n" + "".join(f"{code};1;1;1;1;1\n" for code in lines)
    response = await client.post(
        "/api/v1/markets/EU/supplied-fabric/import",
        files={"file": ("t.csv", body.encode(), "text/csv")},
        headers=_auth(s.platform_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["fabric_via_application"] == [s.code_with]
    assert data["fabric_via_legacy_selector"] == sorted([legacy_direct, legacy_free])
    assert data["without_fabric_category"] == sorted([bare.product_code, other_category.product_code])
