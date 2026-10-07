"""Bloco 02: autorização e auditoria das mudanças de IPI global."""

import asyncio
import inspect
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.deps import require_br_fiscal_admin
from app.api.routers.import_csv import import_product_groups, import_product_types, import_products
from app.api.routers.product_groups import (
    create_product_group,
    delete_product_group,
    update_product_group,
)
from app.api.routers.product_types import (
    create_product_type,
    delete_product_type,
    update_product_type,
)
from app.api.routers.products import create_product, update_product
from app.core.fiscal_audit import record_product_group_event
from app.core.markets import MARKETS, MarketPrincipal
from app.models.product_group import ProductGroup
from app.models.product_group_audit_event import ProductGroupAuditEvent
from app.models.product_type import ProductType
from app.models.product_type_fiscal_audit_event import ProductTypeFiscalAuditEvent
from app.models.product_fiscal_assignment_event import ProductFiscalAssignmentEvent
from app.models.product import Product
from app.models.user import UserRole
from app.schemas.product_group import ProductGroupCreate, ProductGroupUpdate
from app.schemas.product_type import ProductTypeCreate, ProductTypeUpdate
from app.schemas.product import ProductCreate, ProductUpdate


def _principal(market_code: str, role: UserRole) -> MarketPrincipal:
    user = SimpleNamespace(id=uuid.uuid4())
    access = SimpleNamespace(role=role.value)
    return MarketPrincipal(user=user, market=MARKETS[market_code], access=access)


def _db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _audit_event(db: AsyncMock) -> ProductGroupAuditEvent:
    return next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], ProductGroupAuditEvent)
    )


class TestFiscalAdminGuard:
    def test_admin_br_e_autorizado(self):
        principal = _principal("BR", UserRole.admin)
        assert require_br_fiscal_admin(principal=principal) is principal

    @pytest.mark.parametrize(
        ("market", "role"),
        [
            ("EU", UserRole.admin),
            ("BR", UserRole.vendedor),
            ("BR", UserRole.produtos),
            ("BR", UserRole.cadastros),
        ],
    )
    def test_outros_mercados_e_papeis_recebem_403(self, market, role):
        with pytest.raises(HTTPException) as exc:
            require_br_fiscal_admin(principal=_principal(market, role))
        assert exc.value.status_code == 403

    @pytest.mark.parametrize(
        "handler",
        [
            create_product_group,
            update_product_group,
            delete_product_group,
            import_product_groups,
        ],
    )
    def test_quatro_vias_usam_o_mesmo_guard(self, handler):
        dependency = inspect.signature(handler).parameters["principal"].default
        assert dependency.dependency is require_br_fiscal_admin


class TestFiscalAudit:
    def test_evento_recusa_mercado_eu(self):
        db = _db()
        with pytest.raises(ValueError):
            record_product_group_event(
                db,
                product_group_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
                market_code="EU",
                action="updated",
                source="api",
                group_name="BANQUETA",
                old_ipi=Decimal("3.00"),
                new_ipi=Decimal("4.00"),
            )
        db.add.assert_not_called()

    def test_criacao_api_registra_autor_mercado_e_novo_ipi(self):
        async def run():
            db = _db()
            principal = _principal("BR", UserRole.admin)
            await create_product_group(
                payload=ProductGroupCreate(name="BANQUETA", ipi=Decimal("3.25")),
                db=db,
                principal=principal,
            )
            event = _audit_event(db)
            assert event.actor_user_id == principal.user.id
            assert event.market_code == "BR"
            assert event.action == "created"
            assert event.source == "api"
            assert event.old_ipi is None
            assert event.new_ipi == Decimal("3.25")
            db.commit.assert_awaited_once()

        asyncio.run(run())


class TestProductTypeFiscalBoundary:
    @pytest.mark.parametrize("handler", [create_product_type, update_product_type, delete_product_type])
    @pytest.mark.parametrize("role", [UserRole.vendedor, UserRole.produtos, UserRole.cadastros])
    def test_papeis_sem_permissao_fiscal_nao_mutam_tipo_br(self, handler, role):
        async def run():
            db = _db()
            kwargs = {"db": db, "principal": _principal("BR", role), "_": None}
            if handler is create_product_type:
                kwargs["payload"] = ProductTypeCreate(name="BANQUETA")
            elif handler is update_product_type:
                kwargs.update(type_id=uuid.uuid4(), payload=ProductTypeUpdate(name="BANQUETA"))
            else:
                kwargs["type_id"] = uuid.uuid4()
            with pytest.raises(HTTPException) as exc:
                await handler(**kwargs)
            assert exc.value.status_code == 403
            db.execute.assert_not_awaited()
            db.commit.assert_not_awaited()
        asyncio.run(run())


class TestProductFiscalAssignment:
    @pytest.mark.parametrize("handler", [create_product, import_products, import_product_types])
    @pytest.mark.parametrize("role", [UserRole.vendedor, UserRole.produtos, UserRole.cadastros])
    def test_operador_nao_classifica_novo_produto_ou_importa_tipo_br(self, handler, role):
        async def run():
            db = _db()
            principal = _principal("BR", role)
            if handler is create_product:
                kwargs = dict(
                    payload=ProductCreate(
                        product_code="TESTE", description="Teste", type="Mesa",
                        altura=1, largura=1, profundidade=1,
                    ),
                    db=db, current_user=principal.actor, principal=principal,
                )
            else:
                kwargs = dict(file=SimpleNamespace(), db=db, current_user=principal.actor,
                              _=None, principal=principal)
                if handler is import_products:
                    kwargs.pop("_", None)
                else:
                    kwargs.pop("current_user", None)
            with pytest.raises(HTTPException) as exc:
                await handler(**kwargs)
            assert exc.value.status_code == 403
            db.commit.assert_not_awaited()
        asyncio.run(run())

    def test_vendedor_nao_troca_tipo_de_produto_br(self):
        async def run():
            product = Product(id=uuid.uuid4(), market_code="BR", product_code="TESTE",
                              description="Teste", type="Mesa", is_active=True)
            db = _db()
            result = MagicMock()
            result.scalar_one_or_none.return_value = product
            db.execute.return_value = result
            principal = _principal("BR", UserRole.vendedor)
            with pytest.raises(HTTPException) as exc:
                await update_product(
                    product_id=product.id, payload=ProductUpdate(type="Cadeira"), db=db,
                    current_user=principal.actor, principal=principal,
                )
            assert exc.value.status_code == 403
            assert product.type == "Mesa"
            db.commit.assert_not_awaited()
        asyncio.run(run())

    def test_admin_br_registra_troca_de_tipo_antes_do_commit(self):
        async def run():
            product = Product(id=uuid.uuid4(), market_code="BR", product_code="TESTE",
                              description="Teste", type="Mesa", is_active=True,
                              source_version=1)
            db = _db()
            result = MagicMock()
            result.scalar_one_or_none.return_value = product
            result.scalars.return_value.all.return_value = []
            db.execute.return_value = result
            principal = _principal("BR", UserRole.admin)
            old_group, new_group = uuid.uuid4(), uuid.uuid4()
            with (
                patch("app.api.routers.products.product_type_fiscal_snapshot",
                      AsyncMock(side_effect=[(old_group, Decimal("3")), (new_group, Decimal("5"))])),
                patch("app.api.routers.products._validate_product_dimensions", AsyncMock()),
                patch("app.api.routers.products._to_read", return_value=SimpleNamespace()),
            ):
                await update_product(
                    product_id=product.id, payload=ProductUpdate(type="Cadeira"), db=db,
                    current_user=principal.actor, principal=principal,
                )
            event = next(call.args[0] for call in db.add.call_args_list
                         if isinstance(call.args[0], ProductFiscalAssignmentEvent))
            assert (event.old_type, event.new_type) == ("Mesa", "Cadeira")
            assert (event.old_group_id, event.new_group_id) == (old_group, new_group)
            assert (event.old_ipi, event.new_ipi) == (Decimal("3"), Decimal("5"))
            assert event.actor_user_id == principal.user.id
            db.commit.assert_awaited_once()
        asyncio.run(run())

class TestProductTypeFiscalAudit:
    def test_admin_eu_nao_pode_vincular_grupo_br(self):
        async def run():
            db = _db()
            with pytest.raises(HTTPException) as exc:
                await create_product_type(
                    payload=ProductTypeCreate(name="MESA", group_id=uuid.uuid4()),
                    db=db, _=None, principal=_principal("EU", UserRole.admin),
                )
            assert exc.value.status_code == 422
            db.commit.assert_not_awaited()
        asyncio.run(run())

    def test_admin_br_registra_troca_do_grupo_e_das_taxas(self):
        async def run():
            old_group = ProductGroup(id=uuid.uuid4(), name="ANTIGO", ipi=Decimal("3.00"))
            new_group = ProductGroup(id=uuid.uuid4(), name="NOVO", ipi=Decimal("5.00"))
            product_type = ProductType(
                id=uuid.uuid4(), market_code="BR", name="BANQUETA", group_id=old_group.id
            )
            db = _db()
            result = MagicMock()
            result.scalar_one_or_none.return_value = product_type
            db.execute.return_value = result
            db.get.side_effect = lambda model, group_id: old_group if group_id == old_group.id else new_group
            principal = _principal("BR", UserRole.admin)
            await update_product_type(
                type_id=product_type.id,
                payload=ProductTypeUpdate(name="BANQUETA", group_id=new_group.id),
                db=db, _=None, principal=principal,
            )
            event = next(
                call.args[0] for call in db.add.call_args_list
                if isinstance(call.args[0], ProductTypeFiscalAuditEvent)
            )
            assert event.actor_user_id == principal.user.id
            assert event.old_group_id == old_group.id
            assert event.new_group_id == new_group.id
            assert event.old_ipi == Decimal("3.00")
            assert event.new_ipi == Decimal("5.00")
            db.commit.assert_awaited_once()
        asyncio.run(run())

    def test_tipo_br_em_uso_nao_pode_ser_renomeado(self):
        async def run():
            product_type = ProductType(
                id=uuid.uuid4(), market_code="BR", name="Mesa", group_id=uuid.uuid4()
            )
            db = _db()
            type_result = MagicMock()
            type_result.scalar_one_or_none.return_value = product_type
            used_result = MagicMock()
            used_result.scalar_one.return_value = True
            db.execute.side_effect = [type_result, used_result]
            with pytest.raises(HTTPException) as exc:
                await update_product_type(
                    type_id=product_type.id,
                    payload=ProductTypeUpdate(name="Mesa nova", group_id=product_type.group_id),
                    db=db, _=None, principal=_principal("BR", UserRole.admin),
                )
            assert exc.value.status_code == 409
            assert product_type.name == "Mesa"
            db.commit.assert_not_awaited()
        asyncio.run(run())

class TestProductGroupAuditWrites:
    def test_edicao_api_registra_ipi_anterior_e_novo(self):
        async def run():
            group_id = uuid.uuid4()
            group = ProductGroup(
                id=group_id,
                name="BANQUETA",
                ipi=Decimal("3.25"),
            )
            db = _db()
            db.get.return_value = group
            principal = _principal("BR", UserRole.admin)
            await update_product_group(
                group_id=group_id,
                payload=ProductGroupUpdate(ipi=Decimal("4.50")),
                db=db,
                principal=principal,
            )
            event = _audit_event(db)
            assert event.product_group_id == group_id
            assert event.old_ipi == Decimal("3.25")
            assert event.new_ipi == Decimal("4.50")
            assert event.action == "updated"

        asyncio.run(run())

    def test_edicao_apenas_do_nome_nao_finge_mudanca_de_ipi(self):
        async def run():
            group = ProductGroup(id=uuid.uuid4(), name="Mesa", ipi=Decimal("0"))
            db = _db()
            db.get.return_value = group
            await update_product_group(
                group_id=group.id, payload=ProductGroupUpdate(name="Mesas"),
                db=db, principal=_principal("BR", UserRole.admin),
            )
            assert group.name == "Mesas"
            assert group.ipi == Decimal("0")
            db.add.assert_not_called()
            db.commit.assert_awaited_once()
        asyncio.run(run())

    def test_exclusao_api_preserva_id_nome_e_ipi_anterior(self):
        async def run():
            group_id = uuid.uuid4()
            group = ProductGroup(
                id=group_id,
                name="BANQUETA",
                ipi=Decimal("3.25"),
            )
            db = _db()
            db.get.return_value = group
            await delete_product_group(
                group_id=group_id,
                db=db,
                principal=_principal("BR", UserRole.admin),
            )
            event = _audit_event(db)
            assert event.product_group_id == group_id
            assert event.group_name == "BANQUETA"
            assert event.old_ipi == Decimal("3.25")
            assert event.new_ipi is None
            assert event.action == "deleted"
            db.delete.assert_awaited_once_with(group)

        asyncio.run(run())

    def test_importacao_csv_registra_a_origem_e_o_novo_ipi(self):
        async def run():
            db = _db()
            principal = _principal("BR", UserRole.admin)
            with (
                patch(
                    "app.api.routers.import_csv._load_rows",
                    AsyncMock(return_value=[{"name": "BANQUETA", "ipi": "5.00"}]),
                ),
                patch(
                    "app.api.routers.import_csv._acquire_import_lock",
                    AsyncMock(),
                ),
                patch(
                    "app.api.routers.import_csv._load_chunked",
                    AsyncMock(return_value=[]),
                ),
                patch(
                    "app.api.routers.import_csv._finalize",
                    AsyncMock(return_value=True),
                ),
            ):
                result = await import_product_groups(
                    file=SimpleNamespace(),
                    db=db,
                    principal=principal,
                )
            event = _audit_event(db)
            assert result["created"] == 1
            assert event.action == "created"
            assert event.source == "csv"
            assert event.old_ipi is None
            assert event.new_ipi == Decimal("5.00")

        asyncio.run(run())
