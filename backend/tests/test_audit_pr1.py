import inspect
import uuid
from types import SimpleNamespace

from sqlalchemy import delete, update
from sqlalchemy.inspection import inspect as sa_inspect

from app.api.routers.orders import _resolve_max_discount
from app.db.market_scope import add_market_scope
from app.models.catalog import Catalog
from app.models.client import Client, anonymize_client_fields
from app.models.product import ProductSetComponent, ProductSetItem
from app.models.representative import anonymize_representative_fields
from app.models.user import UserRole


def test_market_scope_applies_to_bulk_update_and_delete():
    for statement, flag in ((update(Client), "is_update"), (delete(Client), "is_delete")):
        state = SimpleNamespace(
            session=SimpleNamespace(info={"active_market": "BR"}),
            execution_options={},
            is_select=False,
            is_update=flag == "is_update",
            is_delete=flag == "is_delete",
            bind_mapper=sa_inspect(Client),
            statement=statement,
        )
        add_market_scope(state)
        assert "clients.market_code" in str(state.statement)


def test_anonymization_preserves_valid_br_state():
    client = SimpleNamespace(id=uuid.uuid4(), state="SP")
    representative = SimpleNamespace(id=uuid.uuid4(), state="RJ")
    anonymize_client_fields(client)
    anonymize_representative_fields(representative)
    assert client.state == "SP"
    assert representative.state == "RJ"


def test_internal_sales_inherits_representative_discount_ceiling():
    user = SimpleNamespace(role=UserRole.vendedor, linked_id=None)
    client = SimpleNamespace(max_discount=0)
    rep = SimpleNamespace(max_discount=12)
    assert _resolve_max_discount(user, client, rep) == 12


def test_model_package_exports_complete_domain_models():
    import app.models as models

    assert models.Catalog is Catalog
    assert models.ProductSetItem is ProductSetItem
    assert models.ProductSetComponent is ProductSetComponent


def test_reported_runtime_guards_are_present_at_the_real_seams():
    import app.api.routers.orders as orders
    import app.api.routers.products as products
    import app.api.routers.users as users

    assert "Product.is_active.is_(True)" in inspect.getsource(orders._load_products_and_types)
    assert "delete(Notification)" in inspect.getsource(users.delete_user)
    assert "ProductMarket.is_available" in inspect.getsource(products.delete_product)
