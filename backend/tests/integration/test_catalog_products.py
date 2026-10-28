"""Contratos HTTP P05 de catálogo, produto e RBAC por mercado.

As rotas usam PostgreSQL real pelo harness de integração. A matriz genérica do
plano P05 precisa respeitar as guards atuais do backend:

* POST BR: admin; vendedor/produtos passam a guarda geral, mas falham na guarda
  fiscal de IPI (`require_br_fiscal_admin`).
* POST EU: admin, vendedor e produtos.
* PATCH de campos comuns: admin, vendedor e produtos em BR/EU. PATCH de tipo
  BR exige admin por alterar a atribuição fiscal; em EU os três podem editar.
* DELETE BR/EU: admin e produtos (`_ADMIN`); vendedor não pode excluir.
* representante, cliente (incluindo identidade legada vendedor+linked_id),
  cadastros e executivo não podem criar, editar ou excluir produto.

Essa é a diferença em relação à matriz genérica “papéis permitidos/negados” do
P05; os testes registram os guards efetivos sem alterar a política do backend.
O harness de migrations normaliza o usuário legado para role cliente em
user_markets; `_token` conserva `users.role=vendedor` e `users.linked_id` para
representar esse estado legado junto da autorização atual.

O plano manda que defeito funcional revelado ganhe PR próprio. O defeito visual
já identificado em CadastroPage (controles de mutação sem guarda por papel) foi
registrado em CadastroPage.products.test.tsx; este P05 permanece de testes.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.catalog import Catalog
from app.models.market import PriceList, ProductMarket, ProductPrice
from app.models.product import Product
from app.models.product_group import ProductGroup
from app.models.product_type import ProductType
from app.models.user import UserRole
from tests.factories import (
    make_catalog,
    make_client,
    make_product_group,
    make_product_type,
    make_representative,
    make_user,
    make_user_market,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_EDITOR_ROLES = ("admin", "vendedor", "produtos")
_DENIED_ROLES = ("representante", "cliente", "cliente_legacy", "cadastros", "executivo")
_ALL_ROLES = _EDITOR_ROLES + _DENIED_ROLES


async def _token(db: AsyncSession, role: str, market: str) -> str:
    """Token de mercado com vínculos válidos, inclusive cliente legado."""
    legacy_client = role == "cliente_legacy"
    user_role = UserRole.vendedor if legacy_client else UserRole(role)
    user = await make_user(
        db,
        email=f"p05-{market.lower()}-{role}-{uuid4().hex[:10]}@ilya-test.invalid",
        role=user_role,
        home_market=market,
    )
    rep_id = None
    linked_client_id = None
    link_role = role
    if role == "representante":
        rep_id = (await make_representative(db, market_code=market)).id
    elif role in ("cliente", "cliente_legacy"):
        price_list = (await db.execute(select(PriceList).where(
            PriceList.market_code == market, PriceList.code == "lojista"
        ).execution_options(skip_market_scope=True))).scalar_one()
        client = await make_client(
            db, price_list, market_code=market, name=f"P05 cliente {uuid4().hex[:10]}"
        )
        linked_client_id = client.id
        link_role = "cliente"
        if legacy_client:
            user.linked_id = client.id
    await make_user_market(
        db, user, market_code=market, role=link_role,
        rep_id=rep_id, linked_client_id=linked_client_id,
    )
    token_role = UserRole.vendedor.value if legacy_client else role
    return create_access_token(user.id, token_role, user.auth_version, market)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _dimensions(db: AsyncSession, market: str) -> tuple[ProductGroup, ProductType]:
    suffix = uuid4().hex[:10]
    group = await make_product_group(
        db,
        market_code=market,
        name=f"P05 grupo {market} {suffix}",
        ipi=Decimal("10.00") if market == "BR" else Decimal("0.00"),
    )
    product_type = await make_product_type(
        db, market_code=market, name=f"P05 tipo {market} {suffix}", group=group
    )
    return group, product_type


def _payload(
    market: str,
    code: str,
    catalog_id: str | UUID | None,
    type_name: str,
) -> dict:
    body = {
        "product_code": code,
        "description": f"Descrição {market} inicial",
        "type": type_name,
        "catalog_id": str(catalog_id) if catalog_id else None,
        "is_circular": True,
        "altura": "0.00",
        "largura": "1.20",
        "profundidade": "0.00",
        "price": "100.00",
        "price_lojista": "100.00",
        "price_corporativo": "90.00",
        "price_pvp": "120.00",
        "price_arquiteto": "80.00",
    }
    if market == "EU":
        body.update({
            "description_pt_pt": "Designação PT inicial",
            "description_en": "English name initial",
        })
    return body


async def _create(
    client: AsyncClient,
    db: AsyncSession,
    *,
    market: str,
    token: str,
    code: str,
    catalog: Catalog | None = None,
) -> dict:
    _, product_type = await _dimensions(db, market)
    # Catálogo é obrigatório no produto (catalog_permissions_r21).
    catalog = catalog or await make_catalog(db, market_code=market)
    response = await client.post(
        "/api/v1/products",
        json=_payload(market, code, catalog.id, product_type.name),
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _count_product_code(db: AsyncSession, code: str) -> int:
    return (await db.execute(
        select(func.count()).select_from(Product).where(
            Product.product_code == code
        ).execution_options(skip_market_scope=True)
    )).scalar_one()


async def _product(db: AsyncSession, product_id: str | UUID, market: str) -> Product:
    return (await db.execute(select(Product).where(
        Product.id == UUID(str(product_id)), Product.market_code == market
    ).execution_options(skip_market_scope=True))).scalar_one()


async def test_reg_cat_01_list_pagination_and_cross_market_catalog_are_isolated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ISO-20/21/34: busca paginada por prefixo único independe da base."""
    br_token = await _token(db_session, "admin", "BR")
    eu_token = await _token(db_session, "admin", "EU")
    suffix = uuid4().hex[:10]
    prefix = f"P05-CAT-{suffix}"
    br_catalog = await make_catalog(db_session, market_code="BR", name=f"BR-{suffix}")
    eu_catalog = await make_catalog(db_session, market_code="EU", name=f"EU-{suffix}")

    br = await _create(
        client, db_session, market="BR", token=br_token,
        code=f"{prefix}-AAA", catalog=br_catalog,
    )
    eu = await _create(
        client, db_session, market="EU", token=eu_token,
        code=f"{prefix}-AAA", catalog=eu_catalog,
    )
    br_next = await _create(
        client, db_session, market="BR", token=br_token,
        code=f"{prefix}-ZZZ", catalog=br_catalog,
    )
    eu_next = await _create(
        client, db_session, market="EU", token=eu_token,
        code=f"{prefix}-ZZZ", catalog=eu_catalog,
    )
    assert br["id"] != eu["id"]
    assert br["market_code"] == "BR" and eu["market_code"] == "EU"

    br_page = await client.get(
        "/api/v1/products", params={"q": prefix, "skip": 0, "limit": 1, "include_total": "true"},
        headers=_auth(br_token),
    )
    eu_page = await client.get(
        "/api/v1/products", params={"q": prefix, "skip": 0, "limit": 1, "include_total": "true"},
        headers=_auth(eu_token),
    )
    assert br_page.status_code == eu_page.status_code == 200
    assert br_page.headers["x-total-count"] == "2"
    assert eu_page.headers["x-total-count"] == "2"
    assert [p["id"] for p in br_page.json()] == [br["id"]]
    assert [p["id"] for p in eu_page.json()] == [eu["id"]]
    br_second_page = await client.get(
        "/api/v1/products", params={"q": prefix, "skip": 1, "limit": 1}, headers=_auth(br_token),
    )
    eu_second_page = await client.get(
        "/api/v1/products", params={"q": prefix, "skip": 1, "limit": 1}, headers=_auth(eu_token),
    )
    assert [p["id"] for p in br_second_page.json()] == [br_next["id"]]
    assert [p["id"] for p in eu_second_page.json()] == [eu_next["id"]]

    hidden = await client.get(f"/api/v1/products/{eu['id']}", headers=_auth(br_token))
    assert hidden.status_code == 404

    cross_code = f"{prefix}-CROSS"
    assert await _count_product_code(db_session, cross_code) == 0
    bad_association = await client.post(
        "/api/v1/products",
        json=_payload("BR", cross_code, eu_catalog.id, "Outro"),
        headers=_auth(br_token),
    )
    assert bad_association.status_code in (404, 422), bad_association.text
    assert await _count_product_code(db_session, cross_code) == 0


async def test_reg_prod_01_02_create_br_eu_persists_market_names_prices_and_pending_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REG-PROD-01/02: same SKU persists independently with per-market fields."""
    br_token = await _token(db_session, "admin", "BR")
    eu_token = await _token(db_session, "admin", "EU")
    suffix = uuid4().hex[:10]
    br_catalog = await make_catalog(db_session, market_code="BR", name=f"BR-{suffix}")
    eu_catalog = await make_catalog(db_session, market_code="EU", name=f"EU-{suffix}")
    code = f"P05-CREATE-{suffix}"

    br = await _create(
        client, db_session, market="BR", token=br_token, code=code, catalog=br_catalog,
    )
    eu = await _create(
        client, db_session, market="EU", token=eu_token, code=code, catalog=eu_catalog,
    )
    assert br["id"] != eu["id"]
    assert br["market_code"] == "BR" and eu["market_code"] == "EU"

    br_product = await _product(db_session, br["id"], "BR")
    assert br_product.catalog_id == br_catalog.id
    assert br_product.is_circular is True
    assert br_product.largura == Decimal("1.20")
    assert br_product.price_lojista == Decimal("100.00")
    br_market = (await db_session.execute(select(ProductMarket).where(
        ProductMarket.product_id == br_product.id,
        ProductMarket.market_code == "BR",
    ).execution_options(skip_market_scope=True))).scalar_one()
    assert br_market.description_pt_pt is None and br_market.description_en is None

    eu_product = await _product(db_session, eu["id"], "EU")
    assert eu_product.catalog_id == eu_catalog.id
    eu_market = (await db_session.execute(select(ProductMarket).where(
        ProductMarket.product_id == eu_product.id,
        ProductMarket.market_code == "EU",
    ).execution_options(skip_market_scope=True))).scalar_one()
    assert (eu_market.description_pt_pt, eu_market.description_en) == (
        "Designação PT inicial", "English name initial"
    )
    assert eu_market.vat_status == "pending"
    assert eu_market.vat_rate is None

    eu_prices = (await db_session.execute(
        select(PriceList.code, ProductPrice.amount)
        .join(ProductPrice, ProductPrice.price_list_id == PriceList.id)
        .where(ProductPrice.product_id == eu_product.id, PriceList.market_code == "EU")
        .execution_options(skip_market_scope=True)
    )).all()
    assert {code: amount for code, amount in eu_prices} == {
        "lojista": Decimal("100.00"),
        "corporativo": Decimal("90.00"),
        "pvp": Decimal("120.00"),
        "arquiteto": Decimal("80.00"),
    }
    assert eu["market_prices"]["arquiteto"] == "80.00"


async def test_eu_product_read_sends_only_approved_vat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """O orçamento de Portugal usa o IVA do produto; pendente sai null, Brasil não tem."""
    br_token = await _token(db_session, "admin", "BR")
    eu_token = await _token(db_session, "admin", "EU")
    code = f"P05-VAT-{uuid4().hex[:10]}"
    br = await _create(client, db_session, market="BR", token=br_token, code=code)
    eu = await _create(client, db_session, market="EU", token=eu_token, code=code)

    pending = await client.get(f"/api/v1/products/{eu['id']}", headers=_auth(eu_token))
    assert pending.status_code == 200, pending.text
    assert pending.json()["vat_rate"] is None

    eu_market = (await db_session.execute(select(ProductMarket).where(
        ProductMarket.product_id == UUID(eu["id"]), ProductMarket.market_code == "EU",
    ).execution_options(skip_market_scope=True))).scalar_one()
    approver = await make_user(
        db_session, email=f"p05-vat-{uuid4().hex[:10]}@ilya-test.invalid",
        role=UserRole.admin, home_market="EU",
    )
    eu_market.vat_rate = Decimal("23.00")
    eu_market.vat_status = "approved"
    eu_market.approved_by_user_id = approver.id
    eu_market.approved_at = datetime.now(timezone.utc)
    await db_session.commit()

    approved = await client.get(f"/api/v1/products/{eu['id']}", headers=_auth(eu_token))
    assert approved.json()["vat_rate"] == "23.00"
    brazil = await client.get(f"/api/v1/products/{br['id']}", headers=_auth(br_token))
    assert brazil.json()["vat_rate"] is None


async def test_reg_prod_02_eu_create_missing_translation_returns_422_without_durable_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EU requires PT-PT and EN names; invalid create returns 422 and rolls back."""
    token = await _token(db_session, "admin", "EU")
    suffix = uuid4().hex[:10]
    code = f"P05-EU-SEM-TRADUCAO-{suffix}"
    _, product_type = await _dimensions(db_session, "EU")
    catalog = await make_catalog(db_session, market_code="EU")
    body = _payload("EU", code, catalog.id, product_type.name)
    body.pop("description_en")

    response = await client.post("/api/v1/products", json=body, headers=_auth(token))
    assert response.status_code == 422
    assert "nomes do produto" in response.json()["detail"].lower()
    # A rota pode ter feito flush antes da validação; rollback representa o fim da
    # transação da requisição e comprova que não existe linha persistida.
    await db_session.rollback()
    assert await _count_product_code(db_session, code) == 0


async def test_reg_prod_03_patch_omitted_fields_preserve_br_and_eu_values(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH parcial preserva campos, traduções e preços omitidos em BR/EU."""
    br_token = await _token(db_session, "admin", "BR")
    eu_token = await _token(db_session, "admin", "EU")
    suffix = uuid4().hex[:10]
    br = await _create(
        client, db_session, market="BR", token=br_token, code=f"P05-PATCH-BR-{suffix}"
    )
    eu = await _create(
        client, db_session, market="EU", token=eu_token, code=f"P05-PATCH-EU-{suffix}"
    )

    for market, token, product, description in (
        ("BR", br_token, br, "Descrição BR alterada"),
        ("EU", eu_token, eu, "Descrição EU alterada"),
    ):
        response = await client.patch(
            f"/api/v1/products/{product['id']}",
            json={"description": description},
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text
        stored = await _product(db_session, product["id"], market)
        assert stored.description == description
        assert stored.price_lojista == Decimal("100.00")
        assert stored.price_corporativo == Decimal("90.00")
        pm = (await db_session.execute(select(ProductMarket).where(
            ProductMarket.product_id == stored.id,
            ProductMarket.market_code == market,
        ).execution_options(skip_market_scope=True))).scalar_one()
        if market == "EU":
            assert pm.description_pt_pt == "Designação PT inicial"
            assert pm.description_en == "English name initial"
            architect_list = (await db_session.execute(select(PriceList).where(
                PriceList.market_code == "EU", PriceList.code == "arquiteto"
            ).execution_options(skip_market_scope=True))).scalar_one()
            architect_price = (await db_session.execute(select(ProductPrice).where(
                ProductPrice.product_id == stored.id,
                ProductPrice.price_list_id == architect_list.id,
            ).execution_options(skip_market_scope=True))).scalar_one()
            assert architect_price.amount == Decimal("80.00")


@pytest.mark.parametrize(
    ("market", "role", "allowed"),
    [
        *(("BR", role, role == "admin") for role in _ALL_ROLES),
        *(("EU", role, role in _EDITOR_ROLES) for role in _ALL_ROLES),
    ],
)
async def test_reg_prod_04_post_role_matrix_matches_market_guards(
    client: AsyncClient, db_session: AsyncSession,
    market: str, role: str, allowed: bool,
) -> None:
    """POST matrix: BR admin only after fiscal guard; EU has three editor roles."""
    token = await _token(db_session, role, market)
    suffix = uuid4().hex[:10]
    code = f"P05-POST-{market}-{role}-{suffix}"
    before = await _count_product_code(db_session, code)
    _, product_type = await _dimensions(db_session, market)
    catalog = await make_catalog(db_session, market_code=market)
    response = await client.post(
        "/api/v1/products",
        json=_payload(market, code, catalog.id, product_type.name),
        headers=_auth(token),
    )
    assert response.status_code == (201 if allowed else 403), response.text
    assert await _count_product_code(db_session, code) == (before + 1 if allowed else before)
    if allowed:
        assert response.json()["market_code"] == market


@pytest.mark.parametrize(
    ("market", "role", "allowed"),
    [
        *((market, role, role in _EDITOR_ROLES)
          for market in ("BR", "EU") for role in _ALL_ROLES),
    ],
)
async def test_reg_prod_04_patch_role_matrix_for_common_fields(
    client: AsyncClient, db_session: AsyncSession,
    market: str, role: str, allowed: bool,
) -> None:
    """PATCH common product fields are editor-only in each active market."""
    admin_token = await _token(db_session, "admin", market)
    actor_token = await _token(db_session, role, market)
    suffix = uuid4().hex[:10]
    product = await _create(
        client, db_session, market=market, token=admin_token,
        code=f"P05-PATCH-RBAC-{market}-{role}-{suffix}",
    )
    current_description = (await _product(db_session, product["id"], market)).description
    response = await client.patch(
        f"/api/v1/products/{product['id']}",
        json={"description": f"P05 alteração {role}"},
        headers=_auth(actor_token),
    )
    assert response.status_code == (200 if allowed else 403), response.text
    stored = await _product(db_session, product["id"], market)
    assert stored.description == (f"P05 alteração {role}" if allowed else current_description)


@pytest.mark.parametrize(
    ("market", "role", "allowed"),
    [
        ("BR", "admin", True), ("BR", "vendedor", False), ("BR", "produtos", False),
        ("EU", "admin", True), ("EU", "vendedor", True), ("EU", "produtos", True),
    ],
)
async def test_reg_prod_04_patch_type_role_matrix_includes_br_fiscal_guard(
    client: AsyncClient, db_session: AsyncSession,
    market: str, role: str, allowed: bool,
) -> None:
    """PATCH type BR is fiscal-only; EU follows its regular editor roles."""
    admin_token = await _token(db_session, "admin", market)
    actor_token = await _token(db_session, role, market)
    suffix = uuid4().hex[:10]
    product = await _create(
        client, db_session, market=market, token=admin_token,
        code=f"P05-TYPE-RBAC-{market}-{role}-{suffix}",
    )
    _, new_type = await _dimensions(db_session, market)
    old_type = product["type"]
    response = await client.patch(
        f"/api/v1/products/{product['id']}",
        json={"type": new_type.name},
        headers=_auth(actor_token),
    )
    assert response.status_code == (200 if allowed else 403), response.text
    stored = await _product(db_session, product["id"], market)
    assert stored.type == (new_type.name if allowed else old_type)


@pytest.mark.parametrize(
    ("market", "role", "allowed"),
    [
        *((market, role, role in ("admin", "produtos"))
          for market in ("BR", "EU") for role in _ALL_ROLES),
    ],
)
async def test_reg_prod_04_delete_role_matrix_is_market_scoped_and_non_destructive_on_denial(
    client: AsyncClient, db_session: AsyncSession,
    market: str, role: str, allowed: bool,
) -> None:
    """DELETE is admin/products in BR/EU; every denied role leaves row active."""
    admin_token = await _token(db_session, "admin", market)
    actor_token = await _token(db_session, role, market)
    suffix = uuid4().hex[:10]
    product = await _create(
        client, db_session, market=market, token=admin_token,
        code=f"P05-DELETE-{market}-{role}-{suffix}",
    )
    response = await client.delete(f"/api/v1/products/{product['id']}", headers=_auth(actor_token))
    assert response.status_code == (204 if allowed else 403), response.text
    stored = await _product(db_session, product["id"], market)
    assert stored.is_active is (not allowed)


async def test_eu_sort_by_description_follows_localized_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A ordenação por descrição no EU usa a designação localizada do mercado."""
    token = await _token(db_session, "admin", "EU")
    prefix = f"P05-SORT-{uuid4().hex[:10]}"
    products = []
    for suffix in ("A", "B", "C"):
        products.append(await _create(
            client, db_session, market="EU", token=token,
            code=f"{prefix}-{suffix}",
        ))

    base_descriptions = ("A", "B", "C")
    pt_descriptions = ("Zebra", "Mesa", "Abacate")
    en_descriptions = ("Apple", "Zulu", "Mango")

    for product, base, pt, en in zip(
        products, base_descriptions, pt_descriptions, en_descriptions
    ):
        orm = await _product(db_session, product["id"], "EU")
        pm = (await db_session.execute(
            select(ProductMarket).where(
                ProductMarket.product_id == orm.id,
                ProductMarket.market_code == "EU",
            ).execution_options(skip_market_scope=True)
        )).scalar_one()
        orm.description = base
        pm.description_pt_pt = pt
        pm.description_en = en
    await db_session.commit()

    pt_asc = await client.get(
        "/api/v1/products",
        params={
            "q": prefix,
            "sort_by": "description",
            "sort_dir": "asc",
            "language": "pt-PT",
        },
        headers=_auth(token),
    )
    assert pt_asc.status_code == 200, pt_asc.text
    assert [p["product_code"] for p in pt_asc.json()] == [
        f"{prefix}-C", f"{prefix}-B", f"{prefix}-A"
    ]

    en_asc = await client.get(
        "/api/v1/products",
        params={
            "q": prefix,
            "sort_by": "description",
            "sort_dir": "asc",
            "language": "en-GB",
        },
        headers=_auth(token),
    )
    assert en_asc.status_code == 200, en_asc.text
    assert [p["product_code"] for p in en_asc.json()] == [
        f"{prefix}-A", f"{prefix}-C", f"{prefix}-B"
    ]

    pt_desc = await client.get(
        "/api/v1/products",
        params={
            "q": prefix,
            "sort_by": "description",
            "sort_dir": "desc",
            "language": "pt-PT",
        },
        headers=_auth(token),
    )
    assert pt_desc.status_code == 200, pt_desc.text
    assert [p["product_code"] for p in pt_desc.json()] == [
        f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"
    ]
