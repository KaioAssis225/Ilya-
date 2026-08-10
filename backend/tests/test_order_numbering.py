import asyncio
import uuid
from unittest.mock import AsyncMock

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

        code, orc_id, order_number = await _next_codes(db, owner_id)

        assert code == "PED-0003"
        assert orc_id == "ORC-0042"
        assert order_number == 3
        assert db.execute.await_count == 2
        assert db.execute.await_args_list[0].args[1] == {
            "number_owner_id": str(owner_id)
        }

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


def test_delete_order_is_blocked_by_retention_policy():
    async def run_test():
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await delete_order(uuid.uuid4(), db=db, _=object())

        assert exc_info.value.status_code == 409
        assert "Cancele o pedido" in exc_info.value.detail
        db.execute.assert_not_awaited()
        db.delete.assert_not_awaited()
        db.commit.assert_not_awaited()

    asyncio.run(run_test())
