"""Protótipos no orçamento, grupos de opcionais próprios e bloqueio do Moloni (PR B).

PostgreSQL real, dados sintéticos. O dono monta o orçamento com preço/IVA do
servidor; quem não é dono (ou não tem permissão) recebe 404 como produto
inexistente; o pedido nunca entra na fila do Moloni.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.client import Client
from app.models.market import PriceList, ProductMarket, ProductPrice, UserMarket, VAT_APPROVED
from app.models.moloni import MoloniExportJob
from app.models.order import Order
from app.services import moloni_exporter
from app.services.order_email_jobs import _snapshot_v2
from tests.factories import make_client, make_product, make_product_market
from tests.integration.test_prototypes import (
    PROTOTYPES,
    World,
    _auth,
    _create,
    _platform_headers,
    _png,
    _world,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP = {"skip_market_scope": True}
ORDERS = "/api/v1/orders"


async def _price_list(db: AsyncSession, code: str) -> PriceList:
    return (await db.execute(
        select(PriceList).where(PriceList.market_code == "EU", PriceList.code == code).execution_options(**_SKIP)
    )).scalar_one()


async def _eu_client(db: AsyncSession) -> Client:
    client = await make_client(
        db, await _price_list(db, "lojista"), market_code="EU", name=f"Cliente {uuid.uuid4().hex[:6]}",
    )
    await db.commit()
    return client


async def _normal_product(db: AsyncSession, w: World):
    """Produto EU comum, com IVA aprovado e preço nas listas lojista e PVP."""
    product = await make_product(db, market_code="EU", catalog=w.catalog, description="Produto comum")
    market = await make_product_market(db, product)
    market.vat_rate, market.vat_status = Decimal("23.00"), VAT_APPROVED
    market.approved_by_user_id, market.approved_at = w.admin.id, datetime.now(timezone.utc)
    for code in ("lojista", "pvp"):
        db.add(ProductPrice(
            product_id=product.id, price_list_id=(await _price_list(db, code)).id, amount=Decimal("500.00"),
        ))
    await db.commit()
    return product


def _order_body(client: Client, *codes: str, price_list: str = "pvp", qty: int = 2, **extra) -> dict:
    return {
        "client_id": str(client.id), "price_list_code": price_list,
        "items": [{"product_code": code, "qty": qty} for code in codes], **extra,
    }


async def _quote(client: AsyncClient, who, eu_client: Client, *codes: str, role: str = "vendedor", **kwargs):
    return await client.post(ORDERS, json=_order_body(eu_client, *codes, **kwargs), headers=_auth(who, role))


# ── Orçamento ─────────────────────────────────────────────────────────────────

async def test_dono_orca_protótipo_com_preco_e_iva_do_servidor(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w, vat_rate="6.00")
    eu_client = await _eu_client(db_session)
    created = await _quote(client, w.james, eu_client, proto["product_code"])
    assert created.status_code == 201, created.text
    order = created.json()
    [item] = order["items"]
    assert item["product_code"] == proto["product_code"]
    assert Decimal(str(item["unit_price"])) == Decimal("1500.00")  # lista PVP escolhida
    assert Decimal(str(item["ipi_rate"])) == Decimal("6.00")          # IVA do protótipo
    assert Decimal(str(order["total_value"])) == Decimal("3000.00")
    assert Decimal(str(order["total_with_ipi"])) == Decimal("3180.00")
    assert item["description"] == "Poltrona protótipo"

    lojista = await _quote(client, w.james, eu_client, proto["product_code"], price_list="lojista")
    assert Decimal(str(lojista.json()["items"][0]["unit_price"])) == Decimal("1000.00")


async def test_quem_nao_e_dono_recebe_404_como_produto_inexistente(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    eu_client = await _eu_client(db_session)
    assert (await _quote(client, w.james, eu_client, "PROT-9999999")).status_code == 404
    for who, role in ((w.other, "vendedor"), (w.plain, "vendedor"), (w.admin, "admin")):
        response = await _quote(client, who, eu_client, proto["product_code"], role=role)
        assert response.status_code == 404, (role, response.text)
        assert response.json()["detail"].startswith("Produto")


async def test_quem_perde_a_permissao_nao_orca_mais(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    eu_client = await _eu_client(db_session)
    link = await db_session.get(UserMarket, (w.james.id, "EU"))
    link.can_manage_prototypes = False
    await db_session.commit()
    assert (await _quote(client, w.james, eu_client, proto["product_code"])).status_code == 404


async def test_orcamento_misto_edicao_e_leitura_por_outros(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    normal = await _normal_product(db_session, w)
    eu_client = await _eu_client(db_session)
    created = await _quote(client, w.james, eu_client, proto["product_code"], normal.product_code)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    edited = await client.put(
        f"{ORDERS}/{order_id}",
        json=_order_body(eu_client, proto["product_code"], normal.product_code, qty=3),
        headers=_auth(w.james, "vendedor"),
    )
    assert edited.status_code == 200, edited.text
    assert {Decimal(str(i["qty"])) for i in edited.json()["items"]} == {Decimal("3")}

    # Quem não vê o protótipo ainda lê o orçamento (snapshot), mas não o reedita.
    admin = _auth(w.admin, "admin")
    read = await client.get(f"{ORDERS}/{order_id}", headers=admin)
    assert read.status_code == 200
    assert proto["product_code"] in {i["product_code"] for i in read.json()["items"]}
    blocked = await client.put(
        f"{ORDERS}/{order_id}", json=_order_body(eu_client, proto["product_code"], normal.product_code), headers=admin,
    )
    assert blocked.status_code == 404


async def test_batch_devolve_protótipo_so_ao_dono(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    body = {"product_codes": [proto["product_code"]]}
    mine = await client.post("/api/v1/products/batch", json=body, headers=_auth(w.james, "vendedor"))
    assert [p["product_code"] for p in mine.json()] == [proto["product_code"]]
    assert mine.json()[0]["is_prototype"] is True
    for who, role in ((w.other, "vendedor"), (w.plain, "vendedor"), (w.admin, "admin")):
        theirs = await client.post("/api/v1/products/batch", json=body, headers=_auth(who, role))
        assert theirs.status_code == 200 and theirs.json() == []
    # O catálogo comum continua sem o protótipo, até para o dono.
    listing = await client.get("/api/v1/products", params={"limit": 1000}, headers=_auth(w.james, "vendedor"))
    assert proto["product_code"] not in {p["product_code"] for p in listing.json()}


# ── Pedido: nada de Moloni ────────────────────────────────────────────────────

async def _jobs(db: AsyncSession, order_id: str) -> list[MoloniExportJob]:
    return list((await db.execute(
        select(MoloniExportJob).where(MoloniExportJob.order_id == uuid.UUID(order_id))
    )).scalars().all())


async def test_finalizar_pedido_com_protótipo_nao_entra_na_fila_do_moloni(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    eu_client = await _eu_client(db_session)
    order_id = (await _quote(client, w.james, eu_client, proto["product_code"])).json()["id"]
    admin = _auth(w.admin, "admin")
    finalized = await client.post(f"{ORDERS}/{order_id}/finalize", json={}, headers=admin)
    assert finalized.status_code == 200, finalized.text
    assert await _jobs(db_session, order_id) == []
    history = await client.get(f"{ORDERS}/{order_id}/history", headers=admin)
    assert any("protótipo" in (h.get("details") or "") for h in history.json())

    platform = await _platform_headers(db_session)
    manual = await client.post(f"/api/v1/integrations/moloni/orders/{order_id}/enqueue", headers=platform)
    assert manual.status_code == 422
    assert "protótipo" in manual.json()["detail"]
    assert await _jobs(db_session, order_id) == []


async def test_exportador_recusa_pedido_com_protótipo(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    eu_client = await _eu_client(db_session)
    order_id = uuid.UUID((await _quote(client, w.james, eu_client, proto["product_code"])).json()["id"])
    await client.post(f"{ORDERS}/{order_id}/finalize", json={}, headers=_auth(w.admin, "admin"))
    job = MoloniExportJob(order_id=order_id, status="pending")
    db_session.add(job)
    await db_session.flush()
    with patch.object(moloni_exporter, "_configured", return_value=True), \
         patch.object(moloni_exporter, "active_moloni_connection", AsyncMock(return_value=object())), \
         patch.object(settings, "MOLONI_BLOCKED", False):
        with pytest.raises(moloni_exporter.MoloniError, match="protótipo"):
            await moloni_exporter.deliver_job(db_session, job)


async def test_pedido_normal_continua_na_fila_do_moloni(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    normal = await _normal_product(db_session, w)
    eu_client = await _eu_client(db_session)
    created = await _quote(client, w.admin, eu_client, normal.product_code, role="admin")
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    assert (await client.post(f"{ORDERS}/{order_id}/finalize", json={}, headers=_auth(w.admin, "admin"))).status_code == 200
    assert len(await _jobs(db_session, order_id)) == 1


# ── PDF: o snapshot do pedido enxerga o protótipo do dono ─────────────────────

async def test_snapshot_do_pdf_traz_a_foto_do_protótipo(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    upload = await client.post(
        f"{PROTOTYPES}/{proto['id']}/photos", files={"file": ("a.png", _png(), "image/png")},
        headers=_auth(w.james, "vendedor"),
    )
    assert upload.status_code == 201, upload.text
    eu_client = await _eu_client(db_session)
    created = await _quote(client, w.james, eu_client, proto["product_code"])
    order = (await db_session.execute(select(Order).where(Order.id == uuid.UUID(created.json()["id"])))).scalar_one()
    fresh_client = (await db_session.execute(
        select(Client).where(Client.id == eu_client.id).execution_options(populate_existing=True)
    )).scalar_one()
    snapshot = await _snapshot_v2(db_session, order, fresh_client, None, None, None)
    [entry] = snapshot["products"]
    assert entry["product_code"] == proto["product_code"]
    assert entry["photo_path"] and entry["photo_path"].endswith(".png")


# ── Grupos de opcionais só do protótipo ───────────────────────────────────────

def _group(name: str = "Acabamento do tampo", *options: str) -> dict:
    return {"name": name, "options": [{"name": n} for n in (options or ("Carvalho", "Nogueira"))]}


async def _new_group(client: AsyncClient, proto: dict, headers: dict) -> dict:
    response = await client.post(f"{PROTOTYPES}/{proto['id']}/optional-groups", json=_group(), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_grupo_proprio_do_protótipo_fica_fora_das_listas_gerais(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    group = await _new_group(client, proto, james)
    assert [o["name"] for o in group["options"]] == ["Carvalho", "Nogueira"]

    listed = await client.get(f"{PROTOTYPES}/{proto['id']}/optional-groups", headers=james)
    assert [g["id"] for g in listed.json()] == [group["id"]]
    # Nem o dono vê o grupo nas listas gerais.
    for who, role in ((w.james, "vendedor"), (w.other, "vendedor"), (w.admin, "admin")):
        headers = _auth(who, role)
        categories = await client.get("/api/v1/optional-categories", headers=headers)
        assert group["id"] not in {c["id"] for c in categories.json()}
        optionals = await client.get("/api/v1/optionals", params={"limit": 1000}, headers=headers)
        assert not {o["id"] for o in group["options"]} & {o["id"] for o in optionals.json()}
    # Outro usuário com a permissão não toca no grupo.
    foreign = _auth(w.other, "vendedor")
    assert (await client.get(f"{PROTOTYPES}/{proto['id']}/optional-groups", headers=foreign)).status_code == 404
    assert (await client.delete(f"{PROTOTYPES}/{proto['id']}/optional-groups/{group['id']}", headers=foreign)).status_code == 404


async def test_usar_grupo_proprio_no_orcamento(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    group = await _new_group(client, proto, james)
    carvalho = group["options"][0]
    patched = await client.patch(
        f"{PROTOTYPES}/{proto['id']}",
        json={"optional_applications": [{
            "category_id": group["id"], "name": "Tampo",
            "allowed_optional_ids": [o["id"] for o in group["options"]], "required": True,
        }]},
        headers=james,
    )
    assert patched.status_code == 200, patched.text
    [application] = patched.json()["optional_applications"]
    assert application["category_name"] == "Acabamento do tampo"
    assert {o["color_name"] for o in application["allowed_optionals"]} == {"Carvalho", "Nogueira"}

    eu_client = await _eu_client(db_session)
    body = _order_body(eu_client, proto["product_code"])
    body["items"][0]["optional_choices"] = [{"application_id": application["id"], "optional_id": carvalho["id"]}]
    created = await client.post(ORDERS, json=body, headers=james)
    assert created.status_code == 201, created.text
    [choice] = created.json()["items"][0]["optional_choices"]
    assert choice["optional_name"] == "Carvalho" and choice["application_name"] == "Tampo"
    # O snapshot sobrevive à exclusão do grupo.
    deleted = await client.delete(f"{PROTOTYPES}/{proto['id']}/optional-groups/{group['id']}", headers=james)
    assert deleted.status_code == 204
    after = await client.get(f"{PROTOTYPES}/{proto['id']}", headers=james)
    assert after.json()["optional_applications"] == []
    order = await client.get(f"{ORDERS}/{created.json()['id']}", headers=james)
    assert order.json()["items"][0]["optional_choices"][0]["optional_name"] == "Carvalho"


async def test_grupo_de_um_protótipo_nao_serve_a_outro(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    first = await _create(client, w)
    second = await _create(client, w, description_pt_pt="Outro protótipo")
    james = _auth(w.james, "vendedor")
    group = await _new_group(client, first, james)
    refused = await client.patch(
        f"{PROTOTYPES}/{second['id']}",
        json={"optional_applications": [{
            "category_id": group["id"], "name": "Roubado",
            "allowed_optional_ids": [o["id"] for o in group["options"]],
        }]},
        headers=james,
    )
    assert refused.status_code == 422, refused.text


async def test_grupo_proprio_nao_serve_a_produto_comum(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    group = await _new_group(client, proto, _auth(w.james, "vendedor"))
    normal = await _normal_product(db_session, w)
    response = await client.patch(
        f"/api/v1/products/{normal.id}",
        json={"optional_applications": [{
            "category_id": group["id"], "name": "Intruso",
            "allowed_optional_ids": [o["id"] for o in group["options"]],
        }]},
        headers=_auth(w.admin, "admin"),
    )
    assert response.status_code == 422, response.text


async def test_editar_grupo_proprio_renomeia_e_reconcilia_opcoes(client: AsyncClient, db_session: AsyncSession):
    w = await _world(db_session)
    proto = await _create(client, w)
    james = _auth(w.james, "vendedor")
    group = await _new_group(client, proto, james)
    keep, drop = group["options"]
    url = f"{PROTOTYPES}/{proto['id']}/optional-groups/{group['id']}"
    replaced = await client.put(url, json={
        "name": "Tampo v2",
        "options": [{"id": keep["id"], "name": "Carvalho claro"}, {"name": "Freixo"}],
    }, headers=james)
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["name"] == "Tampo v2"
    assert {o["name"] for o in body["options"]} == {"Carvalho claro", "Freixo"}
    assert drop["id"] not in {o["id"] for o in body["options"]}
    assert keep["id"] in {o["id"] for o in body["options"]}
    repeated = await client.put(url, json={"name": "x", "options": [{"name": "A"}, {"name": "a"}]}, headers=james)
    assert repeated.status_code == 422
    foreign = await client.put(url, json={"name": "x", "options": [{"id": str(uuid.uuid4()), "name": "A"}]}, headers=james)
    assert foreign.status_code == 422


async def test_apagar_protótipo_no_banco_leva_grupo_e_opcoes(client: AsyncClient, db_session: AsyncSession):
    """Hard delete (ex.: downgrade) apaga grupo e opções por ON DELETE CASCADE."""
    w = await _world(db_session)
    proto = await _create(client, w)
    group = await _new_group(client, proto, _auth(w.james, "vendedor"))
    await db_session.execute(text("DELETE FROM products WHERE id = :id"), {"id": proto["id"]})
    left = (await db_session.execute(text(
        "SELECT (SELECT count(*) FROM optional_categories WHERE id = :c), "
        "(SELECT count(*) FROM optionals WHERE prototype_id = :p)"
    ), {"c": group["id"], "p": proto["id"]})).one()
    assert tuple(left) == (0, 0)
