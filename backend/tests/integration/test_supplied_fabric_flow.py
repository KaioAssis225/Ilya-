"""TECIDO FORNECIDO (Portugal) — HTTP + PostgreSQL real.

Contrato:
* a opção só aparece (``supplied_fabric`` no produto) nos produtos importados;
* criar/editar pedido com a escolha usa o preço "sem tecido" da TABELA do
  orçamento, grava a metragem no item e ignora qualquer preço enviado;
* produto sem dado, mercado BR, categoria errada ou mistura com outro tecido
  IBTW → 422 e nenhum resíduo;
* a importação (CSV da planilha, só platform_admin) faz dry-run por padrão,
  arredonda ROUND_HALF_UP, reporta SKU desconhecido sem derrubar o lote.

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
from app.core.supplied_fabric import SUPPLIED_FABRIC_CATEGORY
from app.models.market import PriceList, ProductSuppliedFabric, VAT_APPROVED
from app.models.optional_application import OrderItemOptionalChoice
from app.models.order import Order, OrderItem
from app.models.user import UserRole
from tests.factories import (
    make_application,
    make_client,
    make_optional,
    make_optional_category,
    make_product,
    make_product_group,
    make_product_market,
    make_product_price,
    make_product_type,
    make_user,
    make_user_market,
)
from tests.factories.users import make_platform_permission

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP = {"skip_market_scope": True}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class Scenario:
    token: str
    platform_token: str
    client_id: uuid.UUID
    code_with: str       # tem dado de tecido fornecido
    id_with: uuid.UUID
    code_without: str    # tem aplicação de tecido, mas sem dado
    app_with: uuid.UUID
    app_without: uuid.UUID
    app_second_with: uuid.UUID  # 2ª aplicação de tecido do produto "with"
    app_other: uuid.UUID        # aplicação de outra categoria (pintura) do produto "with"
    linen_id: uuid.UUID
    paint_id: uuid.UUID


async def _price_list(db: AsyncSession, market: str, code: str) -> PriceList:
    return (await db.execute(
        select(PriceList).where(PriceList.market_code == market, PriceList.code == code)
        .execution_options(**_SKIP)
    )).scalar_one()


async def _scenario(db: AsyncSession, market: str = "EU") -> Scenario:
    suffix = uuid.uuid4().hex[:8].upper()
    user = await make_user(
        db, email=f"tf-{suffix.lower()}@ilya-test.invalid", role=UserRole.admin, home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    token = create_access_token(user.id, "admin", user.auth_version, market)
    platform = await make_user(db, email=f"tf-plat-{suffix.lower()}@ilya-test.invalid", role=UserRole.admin)
    await make_platform_permission(db, platform, capability="platform_admin")
    platform_token = create_access_token(platform.id, None, platform.auth_version, None, scope="platform")

    lists = {code: await _price_list(db, market, code) for code in ("lojista", "corporativo")}
    if market == "EU":
        lists["pvp"] = await _price_list(db, "EU", "pvp")
        lists["arquiteto"] = await _price_list(db, "EU", "arquiteto")
    client = await make_client(db, lists["lojista"], market_code=market, name=f"TF Cliente {suffix}")

    group = await make_product_group(
        db, market_code=market, name=f"TF grupo {suffix}",
        ipi=Decimal("10.00") if market == "BR" else Decimal("0"),
    )
    product_type = await make_product_type(db, market_code=market, name=f"TF tipo {suffix}", group=group)
    fabric_cat = await make_optional_category(
        db, market_code=market, code=SUPPLIED_FABRIC_CATEGORY if market == "EU" else f"TEC{suffix}", name="Tecidos IBTW",
    )
    paint_cat = await make_optional_category(db, market_code=market, code=f"PINT{suffix}", name="Pintura")
    linen = await make_optional(db, fabric_cat, color_name="Linho", brand="IBTW")
    paint = await make_optional(db, paint_cat, color_name="Taupe", brand="IBTW")

    async def product(tag: str, amount: str):
        item = await make_product(db, market_code=market, product_code=f"TF{tag}-{suffix}", description=f"Sofá {tag}")
        item.type = product_type.name
        pm = await make_product_market(db, item)
        if market == "EU":
            pm.vat_rate = Decimal("23.00")
            pm.vat_status = VAT_APPROVED
            pm.approved_by_user_id = user.id
            pm.approved_at = datetime.now(timezone.utc)
        for plist in lists.values():
            await make_product_price(db, item, plist, amount=Decimal(amount))
        return item

    with_data = await product("A", "1000.00")
    without_data = await product("B", "900.00")
    app_with = await make_application(db, with_data, fabric_cat, name="Tecido", allowed=[linen], display_order=0)
    app_second = await make_application(db, with_data, fabric_cat, name="Tecido almofadas", allowed=[linen], display_order=1)
    app_other = await make_application(db, with_data, paint_cat, name="Pés", allowed=[paint], display_order=2)
    app_without = await make_application(db, without_data, fabric_cat, name="Tecido", allowed=[linen])
    if market == "EU":
        db.add(ProductSuppliedFabric(
            product_id=with_data.id, linear_meters=Decimal("13.20"),
            price_lojista=Decimal("700.10"), price_corporativo=Decimal("800.20"),
            price_pvp=Decimal("1400.30"), price_arquiteto=Decimal("900.40"),
        ))
    await db.flush()
    s = Scenario(
        token=token, platform_token=platform_token, client_id=client.id,
        code_with=with_data.product_code, id_with=with_data.id, code_without=without_data.product_code,
        app_with=app_with.id, app_without=app_without.id, app_second_with=app_second.id, app_other=app_other.id,
        linen_id=linen.id, paint_id=paint.id,
    )
    await db.commit()
    return s


def _supplied(app_id: uuid.UUID) -> dict:
    return {"application_id": str(app_id), "supplied_fabric": True}


def _both_supplied(s: Scenario) -> list[dict]:
    return [_supplied(s.app_with), _supplied(s.app_second_with)]


def _item(code: str, *choices: dict, **extra) -> dict:
    return {"product_code": code, "qty": 2, "optional_choices": list(choices), **extra}


async def _post(client: AsyncClient, s: Scenario, items: list[dict], **extra):
    return await client.post(
        "/api/v1/orders", json={"client_id": str(s.client_id), "items": items, **extra}, headers=_auth(s.token),
    )


async def _count_orders(db: AsyncSession, s: Scenario) -> int:
    await db.rollback()
    db.expunge_all()
    return (await db.execute(
        select(func.count()).select_from(Order).where(Order.client_id == s.client_id).execution_options(**_SKIP)
    )).scalar_one()


# ── Oferta no catálogo ────────────────────────────────────────────────────────

async def test_catalog_exposes_supplied_fabric_only_for_imported_products(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    response = await client.get("/api/v1/products", params={"limit": 50}, headers=_auth(s.token))
    assert response.status_code == 200, response.text
    by_code = {row["product_code"]: row for row in response.json()}
    fabric = by_code[s.code_with]["supplied_fabric"]
    assert Decimal(str(fabric["linear_meters"])) == Decimal("13.20")
    assert Decimal(str(fabric["prices"]["lojista"])) == Decimal("700.10")
    assert by_code[s.code_without]["supplied_fabric"] is None


# ── Pedido: preço, metragem e anti-adulteração ────────────────────────────────

async def test_order_with_supplied_fabric_uses_sheet_price_and_saves_meters(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(s.code_with, *_both_supplied(s))])
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("700.10")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("13.20")
    assert {choice["optional_name"] for choice in item["optional_choices"]} == {"TECIDO FORNECIDO"}
    assert all(choice["supplied_fabric"] for choice in item["optional_choices"])
    stored = (await db_session.execute(
        select(OrderItem.supplied_fabric_meters).where(OrderItem.id == uuid.UUID(item["id"])).execution_options(**_SKIP)
    )).scalar_one()
    assert stored == Decimal("13.20")


@pytest.mark.parametrize("list_code,expected", [
    ("lojista", "700.10"), ("corporativo", "800.20"), ("pvp", "1400.30"), ("arquiteto", "900.40"),
])
async def test_price_comes_from_the_quote_price_list(
    client: AsyncClient, db_session: AsyncSession, list_code: str, expected: str,
) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(s.code_with, *_both_supplied(s))], price_list_code=list_code)
    assert response.status_code == 201, response.text
    assert Decimal(str(response.json()["items"][0]["unit_price"])) == Decimal(expected)


async def test_order_without_supplied_fabric_keeps_normal_price_and_no_meters(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(
        s.code_with,
        {"application_id": str(s.app_with), "optional_id": str(s.linen_id)},
        {"application_id": str(s.app_second_with), "optional_id": str(s.linen_id)},
    )])
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("1000.00")
    assert item["supplied_fabric_meters"] is None


async def test_client_sent_price_and_meters_are_ignored(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(
        s.code_with, *_both_supplied(s),
        unit_price="1.00", supplied_fabric_meters="999", price="1.00",
    )])
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("700.10")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("13.20")


async def test_discount_and_vat_apply_over_the_sheet_price(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    # Desconto só existe na tabela PVP (teto do admin: 10 %).
    response = await _post(client, s, [_item(s.code_with, *_both_supplied(s), discount="10")], price_list_code="pvp")
    assert response.status_code == 201, response.text
    body = response.json()
    # 1400,30 × 2 un × (1 − 10 %) = 2520,54; IVA 23 % = 579,72 (2 casas, ROUND_HALF_UP)
    assert Decimal(str(body["total_value"])) == Decimal("2520.54")
    assert Decimal(str(body["total_ipi"])) == Decimal("579.72")


# ── Recusas (422) sem resíduo ────────────────────────────────────────────────

async def test_product_without_data_rejects_supplied_fabric(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(s.code_without, _supplied(s.app_without))])
    assert response.status_code == 422
    assert "não aceita TECIDO FORNECIDO" in response.text
    assert await _count_orders(db_session, s) == 0


async def test_supplied_fabric_in_a_non_fabric_application_is_rejected(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(s.code_with, _supplied(s.app_other))])
    assert response.status_code == 422
    assert await _count_orders(db_session, s) == 0


async def test_mixing_supplied_and_catalog_fabric_in_the_same_item_is_rejected(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    response = await _post(client, s, [_item(
        s.code_with, _supplied(s.app_with),
        {"application_id": str(s.app_second_with), "optional_id": str(s.linen_id)},
    )])
    assert response.status_code == 422
    assert "todos os tecidos" in response.text
    assert await _count_orders(db_session, s) == 0


async def test_choice_must_be_exactly_one_of_optional_custom_or_supplied(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    both = {"application_id": str(s.app_with), "optional_id": str(s.linen_id), "supplied_fabric": True}
    response = await _post(client, s, [_item(s.code_with, both)])
    assert response.status_code == 422


async def test_supplied_fabric_is_not_available_in_brazil(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session, market="BR")
    response = await _post(client, s, [_item(s.code_with, _supplied(s.app_with))])
    assert response.status_code == 422
    assert await _count_orders(db_session, s) == 0


# ── Edição recalcula pelo banco ──────────────────────────────────────────────

async def test_edit_switches_price_back_and_forth(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    created = await _post(client, s, [_item(s.code_with, *_both_supplied(s))])
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    normal = await client.put(f"/api/v1/orders/{order_id}", json={"items": [_item(
        s.code_with,
        {"application_id": str(s.app_with), "optional_id": str(s.linen_id)},
        {"application_id": str(s.app_second_with), "optional_id": str(s.linen_id)},
    )]}, headers=_auth(s.token))
    assert normal.status_code == 200, normal.text
    item = normal.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("1000.00") and item["supplied_fabric_meters"] is None
    again = await client.put(f"/api/v1/orders/{order_id}", json={"items": [_item(s.code_with, *_both_supplied(s))]},
                             headers=_auth(s.token))
    assert again.status_code == 200, again.text
    item = again.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("700.10")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("13.20")


async def test_edit_uses_current_database_value_not_the_old_snapshot(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    created = await _post(client, s, [_item(s.code_with, *_both_supplied(s))])
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    source_item_id = created.json()["items"][0]["id"]
    row = await db_session.get(ProductSuppliedFabric, s.id_with)
    row.price_lojista = Decimal("650.00")
    row.linear_meters = Decimal("12.00")
    await db_session.commit()
    edited = await client.put(f"/api/v1/orders/{order_id}", json={"items": [
        # Sem `optional_choices`: o item de origem é copiado com as escolhas dele
        # (caminho da revisão), mas preço e metragem saem do banco de hoje.
        {"product_code": s.code_with, "qty": 2, "source_order_item_id": source_item_id},
    ]}, headers=_auth(s.token))
    assert edited.status_code == 200, edited.text
    item = edited.json()["items"][0]
    assert Decimal(str(item["unit_price"])) == Decimal("650.00")
    assert Decimal(str(item["supplied_fabric_meters"])) == Decimal("12.00")


async def test_choices_snapshot_survives_in_database(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    created = await _post(client, s, [_item(s.code_with, *_both_supplied(s))])
    assert created.status_code == 201, created.text
    rows = (await db_session.execute(
        select(
            OrderItemOptionalChoice.supplied_fabric,
            OrderItemOptionalChoice.optional_id,
            OrderItemOptionalChoice.optional_name,
        )
        .join(OrderItem, OrderItem.id == OrderItemOptionalChoice.order_item_id)
        .where(OrderItem.order_id == uuid.UUID(created.json()["id"])).execution_options(**_SKIP)
    )).all()
    assert len(rows) == 2
    assert all(r.supplied_fabric and r.optional_id is None and r.optional_name == "TECIDO FORNECIDO" for r in rows)


# ── Importação ───────────────────────────────────────────────────────────────

_HEADER = "COD;PVP;LOJISTA;ARQUITETO;CORPORATIVO;MTS TECIDO\n"


async def _import(client: AsyncClient, s: Scenario, body: str, **params):
    return await client.post(
        "/api/v1/markets/EU/supplied-fabric/import",
        params=params,
        files={"file": ("tecido.csv", body.encode("utf-8"), "text/csv")},
        headers=_auth(s.platform_token),
    )


async def _rows(db: AsyncSession) -> int:
    await db.rollback()
    db.expunge_all()
    return (await db.execute(select(func.count()).select_from(ProductSuppliedFabric))).scalar_one()


async def test_import_dry_run_is_the_default_and_writes_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    response = await _import(client, s, _HEADER + f"{s.code_without};100,005;50,004;75,005;60,00;5,5\n")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dry_run"] is True and data["applied"] == 0
    assert data["to_create"] == [s.code_without]
    assert await _rows(db_session) == 1  # só o do cenário


async def test_import_apply_creates_updates_rounds_half_up_and_reports_unknown(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    body = (
        _HEADER
        + f"{s.code_without};100.005;50.004;75.015;60,125;5,5\n"        # criar; arredondar
        + f"{s.code_with};1400.30;700.99;900.40;800.20;13.2\n"           # atualizar só o lojista
        + "ZZ9999;1;1;1;1;1\n"                                          # SKU que não existe no EU
    )
    dry = await _import(client, s, body, dry_run="true")
    assert dry.status_code == 200, dry.text
    assert dry.json()["unknown_skus"] == ["ZZ9999"]
    assert dry.json()["to_update"][0]["sku"] == s.code_with
    assert dry.json()["to_update"][0]["changes"]["price_lojista"] == {"from": "700.10", "to": "700.99"}
    assert await _rows(db_session) == 1
    applied = await _import(client, s, body, dry_run="false")
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] == 2
    await db_session.rollback()
    db_session.expunge_all()
    updated = await db_session.get(ProductSuppliedFabric, s.id_with)
    assert updated.price_lojista == Decimal("700.99")
    created = (await db_session.execute(
        select(ProductSuppliedFabric).where(ProductSuppliedFabric.product_id != s.id_with)
    )).scalars().one()
    assert (created.price_pvp, created.price_lojista, created.price_arquiteto, created.price_corporativo, created.linear_meters) == (
        Decimal("100.01"), Decimal("50.00"), Decimal("75.02"), Decimal("60.13"), Decimal("5.50"),
    )


async def test_import_rejects_malformed_file_without_changing_anything(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    assert (await _import(client, s, _HEADER + f"{s.code_without};abc;1;1;1;5\n", dry_run="false")).status_code == 422
    assert (await _import(client, s, _HEADER + f"{s.code_without};1;1;1;1;0\n", dry_run="false")).status_code == 422
    assert (await _import(client, s, "COD;PVP\nX;1\n")).status_code == 422
    assert await _rows(db_session) == 1


async def test_import_is_platform_admin_only(client: AsyncClient, db_session: AsyncSession) -> None:
    s = await _scenario(db_session)
    response = await client.post(
        "/api/v1/markets/EU/supplied-fabric/import",
        files={"file": ("tecido.csv", (_HEADER + f"{s.code_without};1;1;1;1;1\n").encode(), "text/csv")},
        headers=_auth(s.token),  # token comercial de mercado, não de plataforma
    )
    assert response.status_code in (401, 403)


async def test_import_flags_products_without_a_fabric_application(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    s = await _scenario(db_session)
    extra = await make_product(
        db_session, market_code="EU", product_code=f"TFX-{uuid.uuid4().hex[:6].upper()}", description="Sem aplicação",
    )
    await make_product_market(db_session, extra)
    code = extra.product_code
    await db_session.commit()
    response = await _import(client, s, _HEADER + f"{code};1;1;1;1;1\n")
    assert response.status_code == 200, response.text
    assert response.json()["without_fabric_category"] == [code]
    assert response.json()["fabric_via_application"] == [] and response.json()["fabric_via_legacy_selector"] == []
