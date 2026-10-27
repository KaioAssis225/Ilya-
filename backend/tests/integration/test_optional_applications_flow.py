"""P07 — aplicações independentes de opcionais no pedido (HTTP + PostgreSQL real).

Contrato exercitado (`_resolve_item_choices` em orders.py e `_replace_applications`
em products.py), lido como regra e não como oráculo:

* cada aplicação do produto é uma escolha independente; duas aplicações da
  mesma categoria guardam opções distintas, e duas linhas do mesmo SKU não
  compartilham escolhas;
* aplicação obrigatória ausente → 422; aplicação opcional pode ficar vazia;
* repetir a mesma opção na mesma categoria só passa se TODAS as aplicações
  envolvidas permitem repetição;
* aplicação repetida no payload ou de outro produto → 422;
* opção de outra categoria ou fora do conjunto permitido → 422;
* ISO-21: opção/categoria/produto do outro mercado nunca é associado — 4xx e
  nenhuma referência cruzada gravada;
* rejeição não grava pedido parcial (nenhum Order, OrderItem, escolha ou
  histórico), mesmo quando a primeira linha do payload era válida.

Harness: a rota roda na mesma AsyncSession do teste. Em produção `get_db`
faz rollback quando a rota levanta exceção; o override de integração não faz.
`_discard_failed_request` reproduz esse rollback (só o SAVEPOINT da requisição)
e limpa o identity map antes de qualquer assertiva de banco. Por isso o cenário
é confirmado com `commit()` (RELEASE SAVEPOINT na transação externa do teste) e
os testes guardam apenas IDs primitivos, nunca instâncias ORM expiradas.

Dados 100% sintéticos (e-mails @ilya-test.invalid, nomes genéricos).
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
from app.models.market import PriceList, VAT_APPROVED
from app.models.optional_application import (
    OrderItemOptionalChoice,
    ProductOptionalApplication,
)
from app.models.order import Order, OrderItem
from app.models.order_history import OrderHistory
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

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SKIP_SCOPE = {"skip_market_scope": True}


# ── Cenário sintético ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Scenario:
    market: str
    token: str
    user_id: uuid.UUID
    client_id: uuid.UUID
    product_code: str
    product_id: uuid.UUID
    category_id: uuid.UUID
    category_code: str
    other_category_id: uuid.UUID
    app_feet: uuid.UUID          # "Pés": obrigatória
    app_back: uuid.UUID          # "Encosto": opcional
    opt_taupe: uuid.UUID
    opt_black: uuid.UUID
    opt_white_not_allowed: uuid.UUID
    opt_linen_other_category: uuid.UUID


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seeded_price_list(db: AsyncSession, market: str, code: str) -> PriceList:
    """Listas de preço vêm do seed das migrations (uq market_code+code)."""
    return (await db.execute(
        select(PriceList).where(PriceList.market_code == market, PriceList.code == code)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()


async def _scenario(
    db: AsyncSession,
    market: str,
    *,
    feet_allow_repeat: bool = True,
    back_allow_repeat: bool = True,
) -> Scenario:
    suffix = uuid.uuid4().hex[:8].upper()
    user = await make_user(
        db, email=f"p07-opt-{market.lower()}-{suffix.lower()}@ilya-test.invalid",
        role=UserRole.admin, home_market=market,
    )
    await make_user_market(db, user, market_code=market, role="admin")
    token = create_access_token(user.id, "admin", user.auth_version, market)

    price_list = await _seeded_price_list(db, market, "lojista")
    client = await make_client(db, price_list, market_code=market, name=f"P07 Cliente {suffix}")

    group = await make_product_group(
        db, market_code=market, name=f"P07 grupo {suffix}",
        ipi=Decimal("10.00") if market == "BR" else Decimal("0"),
    )
    product_type = await make_product_type(
        db, market_code=market, name=f"P07 tipo {suffix}", group=group,
    )
    product = await make_product(
        db, market_code=market, product_code=f"P07-{market}-{suffix}",
        description="Poltrona sintética P07",
    )
    product.type = product_type.name
    product_market = await make_product_market(db, product)
    if market == "EU":
        product_market.vat_rate = Decimal("23.00")
        product_market.vat_status = VAT_APPROVED
        product_market.approved_by_user_id = user.id
        product_market.approved_at = datetime.now(timezone.utc)
    await make_product_price(db, product, price_list, amount=Decimal("100.00"))

    paint = await make_optional_category(
        db, market_code=market, code=f"PINT{suffix}", name="Pintura",
    )
    fabric = await make_optional_category(
        db, market_code=market, code=f"TEC{suffix}", name="Tecido",
    )
    taupe = await make_optional(db, paint, color_name="Taupe")
    black = await make_optional(db, paint, color_name="Preto")
    white = await make_optional(db, paint, color_name="Branco")
    linen = await make_optional(db, fabric, color_name="Linho")

    feet = await make_application(
        db, product, paint, name="Pés", name_en="Legs", required=True,
        allow_repeat=feet_allow_repeat, allowed=[taupe, black], display_order=0,
    )
    back = await make_application(
        db, product, paint, name="Encosto", name_en="Backrest", required=False,
        allow_repeat=back_allow_repeat, allowed=[taupe, black], display_order=1,
    )
    await db.flush()
    scenario = Scenario(
        market=market, token=token, user_id=user.id, client_id=client.id,
        product_code=product.product_code, product_id=product.id,
        category_id=paint.id, category_code=paint.code, other_category_id=fabric.id,
        app_feet=feet.id, app_back=back.id,
        opt_taupe=taupe.id, opt_black=black.id,
        opt_white_not_allowed=white.id, opt_linen_other_category=linen.id,
    )
    # RELEASE SAVEPOINT: o cenário sobrevive ao rollback de uma requisição
    # rejeitada, mas continua dentro da transação externa revertida no teardown.
    await db.commit()
    return scenario


def _choice(application_id: uuid.UUID, optional_id: uuid.UUID) -> dict[str, str]:
    return {"application_id": str(application_id), "optional_id": str(optional_id)}


def _item(s: Scenario, *choices: dict[str, str], qty: int = 1, **extra) -> dict:
    return {"product_code": s.product_code, "qty": qty, "optional_choices": list(choices), **extra}


async def _post_order(client: AsyncClient, s: Scenario, items: list[dict]):
    return await client.post(
        "/api/v1/orders",
        json={"client_id": str(s.client_id), "items": items},
        headers=_auth(s.token),
    )


async def _discard_failed_request(db: AsyncSession) -> None:
    """Emula o rollback de `get_db` após exceção e descarta o identity map."""
    await db.rollback()
    db.expunge_all()


async def _assert_no_partial_order(db: AsyncSession, s: Scenario) -> None:
    """Nenhum resíduo do pedido rejeitado: Order, OrderItem, escolha ou histórico."""
    await _discard_failed_request(db)
    orders = (await db.execute(
        select(func.count()).select_from(Order).where(Order.client_id == s.client_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    items = (await db.execute(
        select(func.count()).select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.client_id == s.client_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    choices = (await db.execute(
        select(func.count()).select_from(OrderItemOptionalChoice).where(
            OrderItemOptionalChoice.application_id.in_([s.app_feet, s.app_back])
        ).execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    history = (await db.execute(
        select(func.count()).select_from(OrderHistory)
        .where(OrderHistory.user_id == s.user_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    assert (orders, items, choices, history) == (0, 0, 0, 0), (
        f"Rejeição gravou resíduo: orders={orders} items={items} "
        f"choices={choices} history={history}"
    )


async def _persisted_choices(db: AsyncSession, order_id: str) -> dict[uuid.UUID, set[tuple]]:
    """Mapa order_item_id → {(application_id, optional_id)} lido do banco."""
    rows = (await db.execute(
        select(
            OrderItem.id,
            OrderItemOptionalChoice.application_id,
            OrderItemOptionalChoice.optional_id,
        )
        .join(OrderItemOptionalChoice, OrderItemOptionalChoice.order_item_id == OrderItem.id)
        .where(OrderItem.order_id == uuid.UUID(order_id))
        .execution_options(**_SKIP_SCOPE)
    )).all()
    result: dict[uuid.UUID, set[tuple]] = {}
    for item_id, application_id, optional_id in rows:
        result.setdefault(item_id, set()).add((application_id, optional_id))
    return result


# ── Aplicações independentes ───────────────────────────────────────────────────

@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_reg_opt_two_applications_same_category_keep_independent_choices(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    """Pés=Taupe e Encosto=Preto na mesma categoria; nenhuma escolha contamina a outra."""
    s = await _scenario(db_session, market)

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black)),
    ])
    assert response.status_code == 201, response.text
    body = response.json()

    [item] = body["items"]
    by_application = {
        choice["application_name"]: (choice["category_code"], choice["optional_name"])
        for choice in item["optional_choices"]
    }
    assert by_application == {
        "Pés": (s.category_code, "Taupe"),
        "Encosto": (s.category_code, "Preto"),
    }

    persisted = await _persisted_choices(db_session, body["id"])
    assert persisted == {
        uuid.UUID(item["id"]): {(s.app_feet, s.opt_taupe), (s.app_back, s.opt_black)},
    }


async def test_reg_opt_two_lines_same_sku_do_not_share_choices(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Duas linhas do mesmo SKU com escolhas cruzadas; cada linha guarda as suas."""
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black), qty=1),
        _item(s, _choice(s.app_feet, s.opt_black), _choice(s.app_back, s.opt_taupe), qty=2),
    ])
    assert response.status_code == 201, response.text
    body = response.json()
    item_by_qty = {item["qty"]: uuid.UUID(item["id"]) for item in body["items"]}

    persisted = await _persisted_choices(db_session, body["id"])
    assert persisted == {
        item_by_qty[1]: {(s.app_feet, s.opt_taupe), (s.app_back, s.opt_black)},
        item_by_qty[2]: {(s.app_feet, s.opt_black), (s.app_back, s.opt_taupe)},
    }


# ── Obrigatório × opcional ─────────────────────────────────────────────────────

async def test_reg_opt_optional_application_may_stay_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [_item(s, _choice(s.app_feet, s.opt_black))])
    assert response.status_code == 201, response.text
    body = response.json()

    persisted = await _persisted_choices(db_session, body["id"])
    assert list(persisted.values()) == [{(s.app_feet, s.opt_black)}]


@pytest.mark.parametrize("market", ["BR", "EU"])
async def test_reg_opt_missing_required_application_is_422_without_order(
    client: AsyncClient, db_session: AsyncSession, market: str
) -> None:
    s = await _scenario(db_session, market)

    response = await _post_order(client, s, [_item(s, _choice(s.app_back, s.opt_taupe))])
    assert response.status_code == 422, response.text
    assert "Pés" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


# ── Opção "Customizado" ────────────────────────────────────────────────────────

async def test_custom_choice_fills_required_application_with_user_text(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Em Portugal, Customizado vale em qualquer aplicação, inclusive obrigatória, e guarda o texto."""
    s = await _scenario(db_session, "EU")

    response = await _post_order(client, s, [_item(
        s,
        {"application_id": str(s.app_feet), "custom_text": "  Pés em latão escovado  "},
        _choice(s.app_back, s.opt_taupe),
    )])
    assert response.status_code == 201, response.text
    by_application = {
        choice["application_name"]: (choice["optional_id"], choice["optional_name"], choice["custom_text"])
        for choice in response.json()["items"][0]["optional_choices"]
    }
    assert by_application == {
        "Pés": (None, "Customizado", "Pés em latão escovado"),
        "Encosto": (str(s.opt_taupe), "Taupe", None),
    }


@pytest.mark.parametrize("choice", [
    {"custom_text": "   "},
    {"custom_text": "Latão", "optional_id": "taupe"},
    {},
])
async def test_custom_choice_needs_exactly_text_or_optional(
    client: AsyncClient, db_session: AsyncSession, choice: dict
) -> None:
    """Customizado sem texto, ou texto junto de um opcional, é 422 sem gravar nada."""
    s = await _scenario(db_session, "EU")
    if choice.get("optional_id") == "taupe":
        choice = {**choice, "optional_id": str(s.opt_taupe)}

    response = await _post_order(client, s, [_item(s, {"application_id": str(s.app_feet), **choice})])
    assert response.status_code == 422, response.text
    await _assert_no_partial_order(db_session, s)


@pytest.mark.parametrize("custom", ["application", "legacy"])
async def test_custom_choice_is_refused_in_brazil(
    client: AsyncClient, db_session: AsyncSession, custom: str
) -> None:
    """No Brasil não existe Customizado: nem na aplicação nem no seletor antigo."""
    s = await _scenario(db_session, "BR")
    if custom == "application":
        item = _item(s, {"application_id": str(s.app_feet), "custom_text": "Pés em latão"})
    else:
        item = _item(s, _choice(s.app_feet, s.opt_taupe), opt_categories={"CORDA": "Customizado: corda azul"})

    response = await _post_order(client, s, [item])
    assert response.status_code == 422, response.text
    assert "Portugal" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


# ── Repetição permitida × proibida ─────────────────────────────────────────────

async def test_reg_opt_repeat_allowed_when_both_applications_allow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_taupe)),
    ])
    assert response.status_code == 201, response.text
    persisted = await _persisted_choices(db_session, response.json()["id"])
    assert list(persisted.values()) == [{(s.app_feet, s.opt_taupe), (s.app_back, s.opt_taupe)}]


@pytest.mark.parametrize(
    ("feet_allow_repeat", "back_allow_repeat"),
    [(True, False), (False, True), (False, False)],
    ids=["encosto-proibe", "pes-proibe", "ambas-proibem"],
)
async def test_reg_opt_repeat_forbidden_if_any_application_forbids(
    client: AsyncClient,
    db_session: AsyncSession,
    feet_allow_repeat: bool,
    back_allow_repeat: bool,
) -> None:
    s = await _scenario(
        db_session, "BR",
        feet_allow_repeat=feet_allow_repeat, back_allow_repeat=back_allow_repeat,
    )

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_taupe)),
    ])
    assert response.status_code == 422, response.text
    assert "repetida" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


async def test_reg_opt_distinct_options_pass_even_when_repeat_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Proibir repetição não impede escolhas diferentes na mesma categoria."""
    s = await _scenario(db_session, "BR", feet_allow_repeat=False, back_allow_repeat=False)

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_back, s.opt_black)),
    ])
    assert response.status_code == 201, response.text


async def test_reg_opt_same_application_twice_in_payload_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(s.app_feet, s.opt_black)),
    ])
    assert response.status_code == 422, response.text
    assert "Aplicação inválida ou repetida" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


async def test_reg_opt_application_of_another_product_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = await _scenario(db_session, "BR")
    other = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), _choice(other.app_back, other.opt_taupe)),
    ])
    assert response.status_code == 422, response.text
    assert "Aplicação inválida ou repetida" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


# ── Categoria e conjunto permitido ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "wrong_option",
    ["opt_linen_other_category", "opt_white_not_allowed"],
    ids=["categoria-errada", "fora-do-conjunto-permitido"],
)
async def test_reg_opt_option_outside_application_is_422(
    client: AsyncClient, db_session: AsyncSession, wrong_option: str
) -> None:
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, getattr(s, wrong_option))),
    ])
    assert response.status_code == 422, response.text
    assert "Opção não autorizada em 'Pés'" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


async def test_reg_opt_legacy_selector_for_converted_category_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Categoria convertida em aplicações não aceita o seletor antigo opt_categories."""
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe), opt_categories={s.category_code: "Taupe"}),
    ])
    assert response.status_code == 422, response.text
    assert "Categoria convertida" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)


async def test_reg_opt_valid_first_line_is_not_saved_when_second_line_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sem pedido parcial: linha 1 válida + linha 2 sem obrigatória → nada gravado."""
    s = await _scenario(db_session, "BR")

    response = await _post_order(client, s, [
        _item(s, _choice(s.app_feet, s.opt_taupe)),
        _item(s, _choice(s.app_back, s.opt_black)),
    ])
    assert response.status_code == 422, response.text
    await _assert_no_partial_order(db_session, s)


# ── ISO-21: referências do outro mercado ───────────────────────────────────────

async def test_iso21_option_from_other_market_is_rejected_without_cross_reference(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Opção EU com o MESMO código de categoria, liberada na aplicação BR por
    cadastro corrompido, ainda é recusada no pedido BR."""
    s = await _scenario(db_session, "BR")
    eu_category = await make_optional_category(
        db_session, market_code="EU", code=s.category_code, name="Pintura EU",
    )
    eu_option = await make_optional(db_session, eu_category, color_name="Taupe EU")
    feet = await db_session.get(ProductOptionalApplication, s.app_feet)
    feet.allowed_optionals = [*feet.allowed_optionals, eu_option]
    eu_option_id = eu_option.id
    await db_session.commit()

    response = await _post_order(client, s, [_item(s, _choice(s.app_feet, eu_option_id))])
    assert response.status_code == 422, response.text
    assert "Opcional não existe neste mercado" in response.json()["detail"]
    await _assert_no_partial_order(db_session, s)
    cross = (await db_session.execute(
        select(func.count()).select_from(OrderItemOptionalChoice)
        .where(OrderItemOptionalChoice.optional_id == eu_option_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalar_one()
    assert cross == 0


async def test_iso21_product_code_from_other_market_is_404_without_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s_br = await _scenario(db_session, "BR")
    s_eu = await _scenario(db_session, "EU")

    response = await client.post(
        "/api/v1/orders",
        json={
            "client_id": str(s_br.client_id),
            "items": [{"product_code": s_eu.product_code, "qty": 1}],
        },
        headers=_auth(s_br.token),
    )
    assert response.status_code == 404, response.text
    await _assert_no_partial_order(db_session, s_br)


async def test_iso21_product_application_with_category_from_other_market_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH BR com categoria EU não substitui nem cria aplicação."""
    s_br = await _scenario(db_session, "BR")
    s_eu = await _scenario(db_session, "EU")

    response = await client.patch(
        f"/api/v1/products/{s_br.product_id}",
        json={"optional_applications": [{
            "category_id": str(s_eu.category_id),
            "name": "Pés",
            "required": True,
            "allowed_optional_ids": [str(s_eu.opt_taupe)],
        }]},
        headers=_auth(s_br.token),
    )
    assert response.status_code == 422, response.text
    assert "Categoria de aplicação inválida para o mercado" in response.json()["detail"]

    await _discard_failed_request(db_session)
    applications = (await db_session.execute(
        select(ProductOptionalApplication.id, ProductOptionalApplication.category_id)
        .where(ProductOptionalApplication.product_id == s_br.product_id)
        .execution_options(**_SKIP_SCOPE)
    )).all()
    assert {(row.id, row.category_id) for row in applications} == {
        (s_br.app_feet, s_br.category_id),
        (s_br.app_back, s_br.category_id),
    }


async def test_iso21_product_application_with_option_from_other_market_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Categoria BR válida, mas opção liberada pertence ao EU → recusa sem gravar."""
    s_br = await _scenario(db_session, "BR")
    s_eu = await _scenario(db_session, "EU")

    response = await client.patch(
        f"/api/v1/products/{s_br.product_id}",
        json={"optional_applications": [{
            "category_id": str(s_br.category_id),
            "name": "Pés",
            "required": True,
            "allowed_optional_ids": [str(s_eu.opt_taupe)],
        }]},
        headers=_auth(s_br.token),
    )
    # `_resolve_optionals` responde 400 (não 422) para opção de outro mercado;
    # ISO-21 exige recusa 4xx sem referência cruzada, não um código específico.
    assert response.status_code in (400, 404, 422), response.text

    await _discard_failed_request(db_session)
    applications = (await db_session.execute(
        select(ProductOptionalApplication)
        .where(ProductOptionalApplication.product_id == s_br.product_id)
        .execution_options(**_SKIP_SCOPE)
    )).scalars().all()
    allowed_ids = {option.id for app in applications for option in app.allowed_optionals}
    assert s_eu.opt_taupe not in allowed_ids
    assert {app.id for app in applications} == {s_br.app_feet, s_br.app_back}
