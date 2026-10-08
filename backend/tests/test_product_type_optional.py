"""Tipo de produto é opcional no cadastro.

"Outro" é o valor-sentinela de "sem tipo" (default do modelo e da importação).
Regressão: em Portugal, onde não existe um tipo cadastrado chamado "Outro", o
cadastro de produto sem tipo escolhido falhava com 422 "Tipo de produto não
pertence ao mercado ativo". Tipos reais continuam validados por mercado.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.api.routers import products


class _NoTypeRowDb:
    """Banco onde nenhum tipo existe: qualquer consulta devolve vazio."""

    def __init__(self):
        self.queries = 0

    async def execute(self, _statement):
        self.queries += 1

        class _Result:
            def scalar_one_or_none(self):
                return None

        return _Result()


@pytest.mark.parametrize("market", ["BR", "EU"])
def test_sem_tipo_nao_exige_tipo_cadastrado(market):
    db = _NoTypeRowDb()
    asyncio.run(products._validate_product_dimensions(db, market, product_type=products.NO_PRODUCT_TYPE))
    assert db.queries == 0


def test_tipo_real_inexistente_no_mercado_continua_recusado():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(products._validate_product_dimensions(_NoTypeRowDb(), "EU", product_type="Sofá"))
    assert exc.value.status_code == 422
