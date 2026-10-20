"""Contract tests for optional applications without a production database."""
import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PASSWORD_PEPPER", "test-pepper")

from app.api.routers.orders import _resolve_item_choices, _order_document_content, _items_history_snapshot
from app.api.routers.products import _replace_applications
from app.models.optional_application import ProductOptionalApplication
from app.models.optional_color import OptionalColor
from app.models.optional_category import OptionalCategory
from app.models.product import ProductSetComponent
from app.schemas.order import OrderItemCreate
from app.schemas.product import OptionalApplicationWrite


class Result:
    def __init__(self, rows): self.rows = rows
    def scalars(self): return self
    def all(self): return self.rows


class Session:
    def __init__(self, applications=(), optionals=(), components=(), market="BR"):
        self.market = market
        self.rows = {
            ProductOptionalApplication: list(applications),
            OptionalColor: list(optionals),
            ProductSetComponent: list(components),
        }

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        rows = self.rows[entity]
        if entity is OptionalColor:
            rows = [row for row in rows if row.market_code == self.market]
        return Result(rows)


def fixture(category="PINTURA", required=True, allow_repeat=True, component_id=None, allowed=True):
    product = SimpleNamespace(id=uuid.uuid4())
    cat = SimpleNamespace(code=category, name=category.title())
    optional = SimpleNamespace(id=uuid.uuid4(), market_code="BR", category=category, color_name="Taupe")
    application = SimpleNamespace(
        id=uuid.uuid4(), product_id=product.id, component_id=component_id,
        category=cat, name="Pintura dos pés", name_en="Leg paint",
        required=required, allow_all=False, allow_repeat=allow_repeat,
        allowed_optionals=[optional] if allowed else [], display_order=0,
    )
    return product, application, optional


def item(choices=(), legacy=None, source_id=None):
    return OrderItemCreate(
        product_code="ABC", qty=1, opt_categories=legacy or {},
        optional_choices=[{"application_id": app, "optional_id": option} for app, option in choices],
        source_order_item_id=source_id,
    )


def resolve(product, applications=(), optionals=(), choices=(), components=(), legacy=None, source=None, market="BR"):
    return asyncio.run(_resolve_item_choices(
        Session(applications, optionals, components, market), product, market, item(choices, legacy), source,
    ))


def test_product_without_optionals_and_single_optional_application():
    product, application, optional = fixture()
    assert resolve(product) == []
    rows = resolve(product, [application], [optional], [(application.id, optional.id)])
    assert len(rows) == 1
    assert rows[0].application_name == "Pintura dos pés"
    assert rows[0].category_code == "PINTURA"
    assert rows[0].optional_name == "Taupe"


def test_required_and_optional_applications():
    product, required, optional = fixture()
    another = SimpleNamespace(**{**required.__dict__, "id": uuid.uuid4(), "name": "Pintura do encosto", "required": False})
    with pytest.raises(HTTPException) as error:
        resolve(product, [required, another], [optional])
    assert "Pintura dos pés" in error.value.detail
    assert len(resolve(product, [required, another], [optional], [(required.id, optional.id)])) == 1


def test_same_category_independent_selections_and_repetition():
    product, first, optional = fixture(allow_repeat=True)
    second = SimpleNamespace(**{**first.__dict__, "id": uuid.uuid4(), "name": "Pintura do encosto"})
    choices = [(first.id, optional.id), (second.id, optional.id)]
    assert len(resolve(product, [first, second], [optional], choices)) == 2
    second.allow_repeat = False
    with pytest.raises(HTTPException) as error:
        resolve(product, [first, second], [optional], choices)
    assert "repetida" in error.value.detail


def test_different_categories_can_use_independent_options():
    product, paint, paint_option = fixture()
    _, leather, leather_option = fixture("COURO")
    leather.product_id = product.id
    choices = [(paint.id, paint_option.id), (leather.id, leather_option.id)]
    assert len(resolve(product, [paint, leather], [paint_option, leather_option], choices)) == 2


def test_option_must_belong_to_category_and_allowed_set():
    product, application, optional = fixture(allowed=False)
    with pytest.raises(HTTPException) as error:
        resolve(product, [application], [optional], [(application.id, optional.id)])
    assert "não autorizada" in error.value.detail
    application.allowed_optionals = [optional]
    optional.category = "COURO"
    with pytest.raises(HTTPException) as error:
        resolve(product, [application], [optional], [(application.id, optional.id)])
    assert "não autorizada" in error.value.detail


def test_cross_market_option_and_legacy_category_collision_rejected():
    product, application, optional = fixture()
    with pytest.raises(HTTPException) as error:
        resolve(product, [application], [optional], [(application.id, optional.id)], legacy={"PINTURA": "Taupe"})
    assert "convertida" in error.value.detail
    optional.market_code = "EU"
    with pytest.raises(HTTPException):
        resolve(product, [application], [optional], [(application.id, optional.id)])


def test_eu_application_uses_its_own_catalog_option():
    product, application, optional = fixture()
    optional.market_code = "EU"
    rows = resolve(product, [application], [optional], [(application.id, optional.id)], market="EU")
    assert rows[0].application_name_en == "Leg paint"


def test_component_application_and_repeat_policy_cross_component():
    component_a, component_b = uuid.uuid4(), uuid.uuid4()
    product, first, optional = fixture(component_id=component_a)
    second = SimpleNamespace(**{**first.__dict__, "id": uuid.uuid4(), "component_id": component_b, "allow_repeat": False})
    components = [SimpleNamespace(id=component_a, set_id=product.id, description="Assento"), SimpleNamespace(id=component_b, set_id=product.id, description="Encosto")]
    with pytest.raises(HTTPException) as error:
        resolve(product, [first, second], [optional], [(first.id, optional.id), (second.id, optional.id)], components)
    assert "repetida" in error.value.detail
    assert resolve(product, [first], [optional], [(first.id, optional.id)], components[:1])[0].component_name == "Assento"


def test_old_order_is_unchanged_and_old_signature_content_has_no_new_key():
    product, application, optional = fixture()
    old = SimpleNamespace(product_code="ABC", opt_categories={"PINTURA": "Taupe"}, optional_choices=[])
    incoming = OrderItemCreate(product_code="ABC", qty=1, opt_categories={"PINTURA": "Taupe"}, source_order_item_id=uuid.uuid4())
    assert asyncio.run(_resolve_item_choices(Session([application], [optional]), product, "BR", incoming, old)) == []
    order = SimpleNamespace(
        id=uuid.uuid4(), document_version=1, market_code="BR", code="PED-1", orc_id="ORC-1",
        client_id=uuid.uuid4(), rep_id=None, price_list_code="lojista", currency="BRL", locale="pt-BR",
        is_finalized=False, is_cancelled=False, external_code=None, total_value=1, total_ipi=0,
        total_with_ipi=1, notes=None, items=[SimpleNamespace(
            id=uuid.uuid4(), product_code="ABC", description="Produto", is_circular=False,
            altura=1, largura=1, profundidade=1, qty=1, unit_price=1, discount=0,
            ipi_rate=0, ipi_value=0, tax_label="IPI", currency="BRL", observacao=None,
            opt_categories={"PINTURA": "Taupe"}, optional_choices=[],
        )],
    )
    assert "application_choices" not in _order_document_content(order)["items"][0]


def test_history_keeps_application_and_option_names_as_snapshots():
    choice = SimpleNamespace(
        id=uuid.uuid4(), application_name="Pintura dos pés", application_name_en="Leg paint",
        category_code="PINTURA", category_name="Pintura", optional_name="Taupe",
        component_name="Cadeira", display_order=1,
    )
    snapshot = _items_history_snapshot([SimpleNamespace(
        product_code="ABC", opt_categories={}, optional_choices=[choice],
    )])
    assert snapshot[0]["applications"][0]["component_name"] == "Cadeira"
    assert snapshot[0]["applications"][0]["application_name"] == "Pintura dos pés"


def test_product_application_creation_reuses_master_category_and_option():
    product_id, category_id, optional_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    category = SimpleNamespace(id=category_id, market_code="BR", code="PINTURA", name="Pintura")
    optional = SimpleNamespace(id=optional_id, market_code="BR", category="PINTURA")

    class SaveSession:
        def __init__(self): self.added = []
        async def execute(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            return Result({ProductOptionalApplication: [], OptionalCategory: [category], OptionalColor: [optional]}[entity])
        def add(self, row): self.added.append(row)
        async def delete(self, row): raise AssertionError("nothing to delete")

    db = SaveSession()
    codes = asyncio.run(_replace_applications(
        db, SimpleNamespace(id=product_id), [OptionalApplicationWrite(
            category_id=category_id, name="Pintura dos pés", required=True,
            allowed_optional_ids=[optional_id],
        )], "BR",
    ))
    assert codes == {"PINTURA"}
    assert len(db.added) == 1
    assert db.added[0].product_id == product_id
    assert db.added[0].category_id == category_id
    assert db.added[0].allowed_optionals == [optional]
