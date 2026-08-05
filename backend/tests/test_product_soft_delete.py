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
from unittest.mock import AsyncMock, patch

from app.api.routers.products import delete_product


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


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
            await delete_product(product.id, db=db, _=SimpleNamespace())

            # Desativa e marca frescor — não remove a linha.
            assert product.is_active is False
            assert product.source_version == 2
            db.delete.assert_not_called()
            db.commit.assert_awaited_once()
            # Produto desativado pode ser reativado: a foto não é apagada.
            mock_delete_upload.assert_not_called()

    asyncio.run(run_test())
