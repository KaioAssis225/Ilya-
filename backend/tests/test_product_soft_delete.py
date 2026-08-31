"""Migration/01 + decisão do Alto Comando (05/08/2026): DELETE /products/{id}
deixa de excluir fisicamente e passa a desativar (is_active=False), sem
apagar a foto e incrementando source_version — pré-requisito para o
polling cross-database do Ilya Estoque enxergar produtos desativados.

Mocka a sessão (AsyncMock), sem depender de banco real — mesmo estilo de
tests/test_order_numbering.py e tests/test_discount_validation.py.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routers.products import (
    delete_product,
    get_product,
    get_products_batch,
    list_products,
    update_product,
)
from app.core.markets import MARKETS, MarketPrincipal
from app.models.user import UserRole
from app.schemas.product import ProductBatchRequest, ProductUpdate


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _EmptyResult:
    """Resultado vazio para as rotas de leitura: o que importa aqui é o WHERE."""

    def scalar_one(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return SimpleNamespace(all=lambda: [])


def _capturing_db(wheres: list[str]):
    """Captura só o WHERE de cada consulta.

    Olhar o SQL inteiro não serve: `select(Product)` lista `products.is_active`
    entre as colunas, então a asserção passaria mesmo sem filtro algum.
    """
    async def _execute(stmt):
        wheres.append(str(stmt.whereclause))
        return _EmptyResult()

    db = AsyncMock()
    db.execute = _execute
    return db


ADMIN = SimpleNamespace(role=UserRole.admin, linked_id=None)
BR_PRINCIPAL = MarketPrincipal(user=ADMIN, market=MARKETS["BR"])
EU_PRINCIPAL = MarketPrincipal(user=ADMIN, market=MARKETS["EU"])


def test_delete_product_desativa_em_vez_de_excluir():
    async def run_test():
        product = SimpleNamespace(
            id=uuid.uuid4(),
            photo_path="produtos/cadeira.jpg",
            is_active=True,
            source_version=1,
        )
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(product)

        with patch(
            "app.api.routers.products.delete_upload", new_callable=AsyncMock
        ) as mock_delete_upload:
            await delete_product(
                product.id,
                db=db,
                current_user=ADMIN,
                principal=BR_PRINCIPAL,
            )

            # Desativa e marca frescor — não remove a linha.
            assert product.is_active is False
            assert product.source_version == 2
            db.delete.assert_not_called()
            db.commit.assert_awaited_once()
            # Produto desativado pode ser reativado: a foto não é apagada.
            mock_delete_upload.assert_not_called()

    asyncio.run(run_test())


def test_delete_product_in_europe_removes_only_european_availability():
    async def run_test():
        product = SimpleNamespace(id=uuid.uuid4(), is_active=True, source_version=7)
        availability = SimpleNamespace(is_available=True)
        db = AsyncMock()
        db.execute.side_effect = [_ScalarResult(product), _ScalarResult(availability)]

        await delete_product(
            product.id,
            db=db,
            current_user=ADMIN,
            principal=EU_PRINCIPAL,
        )

        assert availability.is_available is False
        assert product.is_active is True
        assert product.source_version == 7
        db.commit.assert_awaited_once()

    asyncio.run(run_test())


def test_update_product_in_europe_changes_only_three_euro_prices():
    async def run_test():
        product = SimpleNamespace(id=uuid.uuid4())
        price_lists = [
            SimpleNamespace(id=uuid.uuid4(), code="lojista"),
            SimpleNamespace(id=uuid.uuid4(), code="corporativo"),
            SimpleNamespace(id=uuid.uuid4(), code="pvp"),
        ]
        stored_prices = [SimpleNamespace(amount=0) for _ in price_lists]
        product_result = _ScalarResult(product)
        lists_result = MagicMock()
        lists_result.scalars.return_value.all.return_value = price_lists
        db = AsyncMock()
        db.execute.side_effect = [
            product_result,
            lists_result,
            *[_ScalarResult(price) for price in stored_prices],
        ]
        returned = SimpleNamespace(id=product.id)

        with (
            patch(
                "app.api.routers.products._visible_price_profile",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.routers.products._to_market_reads",
                new_callable=AsyncMock,
                return_value=[returned],
            ),
        ):
            result = await update_product(
                product.id,
                ProductUpdate(
                    price_lojista=100,
                    price_corporativo=200,
                    price_pvp=300,
                ),
                db=db,
                current_user=ADMIN,
                principal=EU_PRINCIPAL,
            )

        assert [price.amount for price in stored_prices] == [100, 200, 300]
        assert result is returned
        db.commit.assert_awaited_once()

    asyncio.run(run_test())


def test_update_product_in_europe_keeps_separate_portuguese_and_english_names():
    async def run_test():
        product = SimpleNamespace(id=uuid.uuid4())
        price_lists = [
            SimpleNamespace(id=uuid.uuid4(), code=code)
            for code in ("lojista", "corporativo", "pvp")
        ]
        lists_result = MagicMock()
        lists_result.scalars.return_value.all.return_value = price_lists
        localized = SimpleNamespace(description_pt_pt=None, description_en=None)
        localized_result = MagicMock()
        localized_result.scalar_one.return_value = localized
        db = AsyncMock()
        db.execute.side_effect = [
            _ScalarResult(product),
            lists_result,
            localized_result,
        ]

        with (
            patch("app.api.routers.products._visible_price_profile", new_callable=AsyncMock, return_value=None),
            patch("app.api.routers.products._to_market_reads", new_callable=AsyncMock, return_value=[product]),
        ):
            await update_product(
                product.id,
                ProductUpdate(
                    description_pt_pt="BANCO ALTO LOTUS SEM BRAÇOS",
                    description_en="LOTUS BAR STOOL WITHOUT ARMS",
                ),
                db=db,
                current_user=ADMIN,
                principal=EU_PRINCIPAL,
            )

        assert localized.description_pt_pt == "BANCO ALTO LOTUS SEM BRAÇOS"
        assert localized.description_en == "LOTUS BAR STOOL WITHOUT ARMS"
        db.commit.assert_awaited_once()

    asyncio.run(run_test())


class TestLeituraEscondeDesativado:
    """Desativar só significa alguma coisa se a leitura filtrar.

    Sem isto o DELETE vira no-op: o front invalida a query, refaz a busca e o
    produto "excluído" reaparece na lista.
    """

    def test_catalogo_filtra_desativado_na_busca_e_na_contagem(self):
        async def run_test():
            wheres: list[str] = []
            await list_products(
                response=SimpleNamespace(headers={}),
                skip=0,
                limit=100,
                q=None,
                product_type=None,
                group_id=None,
                include_total=True,
                sort_by="product_code",
                sort_dir="asc",
                db=_capturing_db(wheres),
                current_user=ADMIN,
                principal=BR_PRINCIPAL,
            )
            # Duas consultas: a contagem do X-Total-Count e a página em si. Um
            # total maior que a página quebraria a paginação do catálogo.
            assert len(wheres) == 2
            assert all("is_active" in w for w in wheres)

        asyncio.run(run_test())

    def test_detalhe_de_produto_desativado_responde_404(self):
        async def run_test():
            wheres: list[str] = []
            with pytest.raises(HTTPException) as exc:
                await get_product(
                    uuid.uuid4(),
                    db=_capturing_db(wheres),
                    current_user=ADMIN,
                    principal=BR_PRINCIPAL,
                )
            assert exc.value.status_code == 404
            assert "is_active" in wheres[0]

        asyncio.run(run_test())

    def test_batch_nao_devolve_desativado(self):
        async def run_test():
            wheres: list[str] = []
            resultado = await get_products_batch(
                ProductBatchRequest(product_codes=["ABC123"]),
                db=_capturing_db(wheres),
                current_user=ADMIN,
                principal=BR_PRINCIPAL,
            )
            assert resultado == []
            assert "is_active" in wheres[0]

        asyncio.run(run_test())
