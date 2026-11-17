"""Regras do mercado EU depois do IVA único (decisão do responsável).

O IVA deixou de ser por produto: é uma taxa única do mercado, aplicada só no
total (ver `tests/integration/test_eu_single_vat.py` para o cálculo). Aqui, no
mesmo estilo mockado dos demais testes (AsyncMock, sem banco):

1. A importação do catálogo EU não exige, não lê e não grava IVA por produto.
2. A ativação da Europa exige a taxa única configurada (e não mais SKU aprovado).
3. Quem aprovou IVA por produto no passado continua protegido contra exclusão
   de conta (a trilha dos dados antigos é preservada).
"""
import asyncio
import io
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy.dialects import postgresql
from starlette.datastructures import UploadFile

from app.api.routers.markets import activate_europe, import_europe_catalog
from app.api.routers.auth import delete_my_account
from app.api.routers.users import delete_user
from app.core.eu_vat import normalize_vat_rate, total_vat
from app.schemas.auth import ReauthenticationRequest


ADMIN = SimpleNamespace(id=uuid.uuid4(), role="admin")


def _upload(csv_text: str) -> UploadFile:
    # Argumentos nomeados: compatível com a assinatura antiga e a nova do
    # Starlette (ordem posicional de `file`/`filename` mudou entre versões).
    return UploadFile(file=io.BytesIO(csv_text.encode("utf-8")), filename="europa.csv")


def _price_lists():
    return [
        SimpleNamespace(id=uuid.uuid4(), code=code, currency="EUR")
        for code in ("lojista", "corporativo", "pvp", "arquiteto")
    ]


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _CountResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _RateResult:
    """Resultado de `select(Market.vat_rate)`: a taxa única (ou None)."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


# ---------------------------------------------------------------------------
# 1. Importação não mexe em IVA
# ---------------------------------------------------------------------------
async def _import(csv_text: str):
    pid1, pid2 = uuid.uuid4(), uuid.uuid4()
    statements = []

    async def _execute(stmt):
        statements.append(stmt)
        index = len(statements)
        if index == 1:
            return _AllResult([(pid1, "EU-1"), (pid2, "EU-2")])
        if index == 2:
            return _ScalarsResult(_price_lists())
        return MagicMock()

    db = AsyncMock()
    db.execute = _execute
    result = await import_europe_catalog(file=_upload(csv_text), db=db, _=ADMIN)
    return result, statements


def _market_upserts(statements):
    return [
        s for s in statements
        if getattr(getattr(s, "table", None), "name", None) == "product_markets"
    ]


def test_import_sem_coluna_vat_rate_e_aceito_e_nao_grava_iva():
    async def run():
        csv_text = (
            "product_code;lojista;corporativo;pvp;arquiteto\n"
            "EU-1;100;90;150;120\n"
            "EU-2;100;90;150;120\n"
        )
        result, statements = await _import(csv_text)

        assert result["imported"] == 2
        assert "pending_vat_approval" not in result
        # A busca de produtos não junta product_groups: sem herança do IPI.
        assert "product_groups" not in str(statements[0])
        upserts = _market_upserts(statements)
        assert len(upserts) == 2
        for stmt in upserts:
            sql = str(stmt.compile(dialect=postgresql.dialect()))
            assert "vat_rate" not in sql
            assert "vat_status" not in sql
            assert "approved_by_user_id" not in sql

    asyncio.run(run())


def test_import_com_coluna_vat_rate_antiga_ignora_o_valor():
    async def run():
        # Planilha antiga: a coluna existe (inclusive vazia ou inválida) e é ignorada.
        csv_text = (
            "product_code;lojista;corporativo;pvp;arquiteto;vat_rate\n"
            "EU-1;100;90;150;120;23\n"
            "EU-2;100;90;150;120;\n"
        )
        result, statements = await _import(csv_text)

        assert result["imported"] == 2
        for stmt in _market_upserts(statements):
            assert "vat_rate" not in str(stmt.compile(dialect=postgresql.dialect()))

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Ativação exige a taxa única do mercado
# ---------------------------------------------------------------------------
def test_activate_recusa_eu_sem_taxa_de_iva_configurada():
    async def run():
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),                         # clientes sem país
            _CountResult(0),                         # representantes sem país
            _CountResult(0),                         # dimensões EU válidas
            _CountResult(1),                         # disponíveis
            _AllResult([(uuid.uuid4(), 4)]),         # com as 4 listas
            _RateResult(None),                       # taxa única ausente
        ]
        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)
        assert exc.value.status_code == 409
        assert "IVA" in exc.value.detail
        db.commit.assert_not_called()

    asyncio.run(run())


def test_activate_recusa_catalogo_eu_vazio():
    async def run():
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),
            _CountResult(0),
            _CountResult(0),
            _CountResult(0),
            _AllResult([]),
            _RateResult(Decimal("23.00")),
        ]
        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)
        assert exc.value.status_code == 409
        assert "SKU" in exc.value.detail
        db.commit.assert_not_called()

    asyncio.run(run())


def test_activate_passa_com_taxa_de_iva_e_sem_aprovacao_por_sku():
    async def run():
        market = SimpleNamespace(is_enabled=False)
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),
            _CountResult(0),
            _CountResult(0),
            _CountResult(1),                         # disponíveis
            _AllResult([(uuid.uuid4(), 4)]),         # com as 4 listas
            _RateResult(Decimal("23.00")),           # taxa única configurada
        ]
        db.get = AsyncMock(return_value=market)

        result = await activate_europe(db=db, _=ADMIN)

        assert market.is_enabled is True
        assert result["enabled"] is True
        db.commit.assert_awaited_once()

    asyncio.run(run())


def test_activate_recusa_cadastro_eu_sem_pais():
    async def run():
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(1),  # cliente sem país
            _CountResult(0),
        ]

        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)

        assert exc.value.status_code == 409
        assert "sem país" in exc.value.detail
        db.commit.assert_not_called()

    asyncio.run(run())


def test_activate_recusa_dimensao_de_produto_fora_do_mercado_eu():
    async def run():
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),
            _CountResult(0),
            _CountResult(1),  # referência cruzada detectada
        ]

        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)

        assert exc.value.status_code == 409
        assert "isolados" in exc.value.detail
        db.commit.assert_not_called()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Cálculo e validação da taxa única (puros)
# ---------------------------------------------------------------------------
class TestTotalVat:
    def test_taxa_sobre_o_subtotal(self):
        assert total_vat(Decimal("200.00"), Decimal("23.00")) == Decimal("46.00")

    def test_arredonda_uma_vez_na_base_total(self):
        # 99,99 × 23% = 22,9977 → 23,00.
        assert total_vat(Decimal("99.99"), Decimal("23.00")) == Decimal("23.00")
        # 0,20 × 23% = 0,046 → 0,05 (linha a linha dariam 0,02 + 0,02).
        assert total_vat(Decimal("0.20"), Decimal("23.00")) == Decimal("0.05")

    def test_meio_centavo_sobe(self):
        assert total_vat(Decimal("0.50"), Decimal("1.00")) == Decimal("0.01")

    def test_isento_e_zero(self):
        assert total_vat(Decimal("200.00"), Decimal("23.00"), exempt=True) == Decimal("0.00")

    def test_taxa_zero(self):
        assert total_vat(Decimal("200.00"), Decimal("0")) == Decimal("0.00")


class TestNormalizeVatRate:
    @pytest.mark.parametrize("value", ["0", "23", "23.5", "100", "7.25"])
    def test_aceita_ate_duas_casas_entre_0_e_100(self, value):
        assert normalize_vat_rate(Decimal(value)) == Decimal(value).quantize(Decimal("0.01"))

    @pytest.mark.parametrize("value", ["-0.01", "100.01", "23.001", "NaN", "Infinity"])
    def test_recusa_fora_da_faixa_ou_com_mais_casas(self, value):
        with pytest.raises(HTTPException) as exc:
            normalize_vat_rate(Decimal(value))
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# 3. Quem aprovou IVA no passado segue protegido contra exclusão de conta
# ---------------------------------------------------------------------------
def test_aprovador_com_taxa_ativa_nao_pode_ser_excluido():
    async def run():
        target_id = uuid.uuid4()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = SimpleNamespace(id=target_id)
        approval_result = MagicMock()
        approval_result.scalar_one_or_none.return_value = uuid.uuid4()
        db = AsyncMock()
        db.execute.side_effect = [user_result, approval_result]

        with pytest.raises(HTTPException) as exc:
            await delete_user(
                target_id,
                db=db,
                platform=SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4())),
            )

        assert exc.value.status_code == 409
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    asyncio.run(run())


def test_aprovador_nao_pode_excluir_a_propria_conta():
    async def run():
        db = AsyncMock()
        approval_result = MagicMock()
        approval_result.scalar_one_or_none.return_value = uuid.uuid4()
        db.execute.return_value = approval_result
        current_user = SimpleNamespace(id=uuid.uuid4())

        with patch("app.api.routers.auth._require_reauthentication"):
            with pytest.raises(HTTPException) as exc:
                await delete_my_account(
                    request=Request({
                        "type": "http",
                        "path": "/api/v1/auth/me",
                        "method": "DELETE",
                        "headers": [],
                        "client": ("127.0.0.1", 1234),
                    }),
                    response=Response(),
                    body=ReauthenticationRequest(password="senha-local"),
                    db=db,
                    current_user=current_user,
                )

        assert exc.value.status_code == 409
        db.delete.assert_not_called()
        db.commit.assert_not_called()

    asyncio.run(run())
