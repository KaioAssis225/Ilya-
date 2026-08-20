import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.routers.orders import _get_order, _next_codes, delete_order


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _RowsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)


def test_next_codes_uses_owner_sequence_and_global_orc():
    async def run_test():
        owner_id = uuid.uuid4()
        db = AsyncMock()
        db.execute.side_effect = [
            _ScalarResult(3),
            _ScalarResult(42),
        ]

        code, orc_id, order_number = await _next_codes(db, owner_id, "EU")

        assert code == "PED-0003"
        assert orc_id == "ORC-0042"
        assert order_number == 3
        assert db.execute.await_count == 2
        assert db.execute.await_args_list[0].args[1] == {
            "market_code": "EU", "number_owner_id": str(owner_id)
        }
        assert db.execute.await_args_list[1].args[1] == {"market_code": "EU"}

    asyncio.run(run_test())


def test_ped_lookup_rejects_ambiguous_code_between_users():
    async def run_test():
        db = AsyncMock()
        db.execute.return_value = _RowsResult([object(), object()])

        with pytest.raises(HTTPException) as exc_info:
            await _get_order(db, "PED-0001")

        assert exc_info.value.status_code == 409
        assert "ORC" in exc_info.value.detail

    asyncio.run(run_test())


class TestExclusaoDePedido:
    """Exclusão física reaberta para o admin (decisão do Alto Comando, 13/08).

    O ponto sensível não é apagar: é avisar. O serviço Estoque mantém projeção
    por ID e detecta mudança por `source_version` — um DELETE puro sumiria com
    a linha sem sinal nenhum, deixando a cópia de lá órfã. O evento tem de ser
    enfileirado na mesma transação, antes do commit.
    """

    @staticmethod
    def _db_com_pedido(order):
        resultado = AsyncMock()
        resultado.scalar_one_or_none = lambda: order
        db = AsyncMock()
        db.execute.return_value = resultado
        # `session.add` é síncrono no SQLAlchemy; deixá-lo como AsyncMock
        # devolveria uma corrotina nunca aguardada e mascararia a ordem real
        # das chamadas.
        db.add = MagicMock()
        return db

    def test_pedido_inexistente_recebe_404(self):
        async def run_test():
            resultado = AsyncMock()
            resultado.scalar_one_or_none = lambda: None
            db = AsyncMock()
            db.execute.return_value = resultado

            with pytest.raises(HTTPException) as exc_info:
                await delete_order(uuid.uuid4(), db=db, current_user=_admin())

            assert exc_info.value.status_code == 404
            db.delete.assert_not_awaited()

        asyncio.run(run_test())

    def test_exclusao_apaga_e_faz_commit(self):
        async def run_test():
            order = _pedido()
            db = self._db_com_pedido(order)

            await delete_order(order.id, db=db, current_user=_admin())

            db.delete.assert_awaited_once_with(order)
            db.commit.assert_awaited_once()

        asyncio.run(run_test())

    def test_exclusao_enfileira_evento_para_o_estoque(self):
        """Sem este evento o consumidor externo nunca fica sabendo."""
        async def run_test():
            order = _pedido()
            db = self._db_com_pedido(order)

            await delete_order(order.id, db=db, current_user=_admin())

            enfileirados = [
                chamada.args[0] for chamada in db.add.call_args_list
            ]
            eventos = [
                linha for linha in enfileirados
                if getattr(linha, "event_type", None) == "order.deleted"
            ]
            assert len(eventos) == 1, "faltou o aviso de exclusão na outbox"
            dados = eventos[0].payload["data"]
            assert dados["order_id"] == str(order.id)
            assert dados["code"] == order.code

        asyncio.run(run_test())

    def test_evento_entra_antes_do_commit(self):
        """Se o evento fosse gravado depois, um erro deixaria o Estoque cego."""
        async def run_test():
            order = _pedido()
            db = self._db_com_pedido(order)
            ordem_das_chamadas = []
            db.add.side_effect = lambda _linha: ordem_das_chamadas.append("add")
            db.commit.side_effect = lambda: ordem_das_chamadas.append("commit")

            await delete_order(order.id, db=db, current_user=_admin())

            assert ordem_das_chamadas.index("add") < ordem_das_chamadas.index("commit")

        asyncio.run(run_test())


def _admin():
    return SimpleNamespace(id=uuid.uuid4())


def _pedido():
    return SimpleNamespace(
        id=uuid.uuid4(),
        code="PED-0007",
        orc_id="ORC-0007",
        client_id=uuid.uuid4(),
        is_finalized=False,
    )
