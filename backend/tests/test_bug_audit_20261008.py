import inspect
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace

from sqlalchemy import delete, update
from sqlalchemy.inspection import inspect as sa_inspect

from app.api.routers.orders import _order_document_hash, _resolve_max_discount
from app.db.market_scope import add_market_scope
from app.models.catalog import Catalog
from app.models.client import Client, anonymize_client_fields
from app.models.client_access_invitation import ClientAccessInvitation
from app.models.market import ProductMarket
from app.models.order import Order, OrderItem
from app.models.order_signature_evidence import OrderSignatureEvidence
from app.models.product import Product, ProductSetComponent, ProductSetItem
from app.models.refresh_token import RefreshToken
from app.models.representative import Representative, anonymize_representative_fields
from app.models.user import User, UserRole


def _order_for_hash() -> Order:
    order = Order(
        id=uuid.uuid4(), market_code="BR", price_list_code="lojista",
        currency="BRL", locale="pt-BR", code="PED-0001",
        number_owner_id=uuid.uuid4(), order_number=1, orc_id="ORC-0001",
        client_id=uuid.uuid4(), rep_id=None, total_value=100,
        total_ipi=5, total_with_ipi=105, notes=None,
        is_finalized=False, is_cancelled=False, external_code=None,
        document_version=1,
    )
    order.items = []
    return order


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


def test_finalization_metadata_does_not_change_signed_document_hash():
    order = _order_for_hash()
    signed_hash = _order_document_hash(order)
    order.is_finalized = True
    order.external_code = "ERP-123"
    order.document_version += 1
    assert _order_document_hash(order) == signed_hash


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


def test_database_relationships_have_expected_foreign_keys():
    invitation_targets = {fk.target_fullname for fk in ClientAccessInvitation.__table__.foreign_keys}
    assert {"users.id", "clients.id"}.issubset(invitation_targets)
    evidence_targets = {fk.target_fullname for fk in OrderSignatureEvidence.__table__.foreign_keys}
    assert {"users.id", "signature_invitations.id"}.issubset(evidence_targets)
    order_item_fk = next(iter(OrderItem.__table__.c.order_id.foreign_keys))
    assert order_item_fk.ondelete == "CASCADE"
    set_item_fk = next(iter(ProductSetItem.__table__.c.product_id.foreign_keys))
    assert set_item_fk.ondelete == "CASCADE"


def test_refresh_token_model_matches_physical_schema_contract():
    assert RefreshToken.__table__.c.token_hash.type.length == 512
    assert "updated_at" in RefreshToken.__table__.c


def test_model_package_exports_complete_domain_models():
    import app.models as models

    assert models.Catalog is Catalog
    assert models.ProductSetItem is ProductSetItem
    assert models.ProductSetComponent is ProductSetComponent


def test_high_frequency_foreign_keys_have_indexes():
    expected = {
        "orders": {"supersedes_order_id"},
        "clients": {"price_list_id"},
        "product_markets": {"approved_by_user_id"},
    }
    tables = {
        "orders": Order.__table__,
        "clients": Client.__table__,
        "product_markets": ProductMarket.__table__,
    }
    for table_name, columns in expected.items():
        indexed = {col.name for index in tables[table_name].indexes for col in index.columns}
        assert columns <= indexed


def test_offline_alembic_can_compile_without_database_environment():
    env = os.environ.copy()
    for key in ("DATABASE_URL", "PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGPORT"):
        env.pop(key, None)
    env.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-characters")
    env.setdefault("PASSWORD_PEPPER", "test-password-pepper")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_reported_runtime_guards_are_present_at_the_real_seams():
    from app.api.routers import optional_categories, orders, products, users

    assert "Product.is_active.is_(True)" in inspect.getsource(orders._load_products_and_types)
    assert "OptionalColor.category == cat.code" in inspect.getsource(optional_categories.delete_optional_category)
    assert "delete(Notification)" in inspect.getsource(users.delete_user)
    assert "ProductMarket.is_available" in inspect.getsource(products.delete_product)
    assert "order.is_finalized" in inspect.getsource(orders.sign_representative)
    assert "order.is_finalized" in inspect.getsource(orders.sign_client)
    assert "order.is_finalized" in inspect.getsource(orders.sign_with_token)


def test_legacy_counter_is_replaced_by_market_global_numbering():
    from app.api.routers import orders

    source = inspect.getsource(orders._next_codes)
    assert "number_owner_id" not in source.split("ON CONFLICT", 1)[1].split("RETURNING", 1)[0]
