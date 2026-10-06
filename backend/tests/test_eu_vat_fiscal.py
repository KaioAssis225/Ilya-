"""Regra fiscal do IVA europeu (decisão do responsável).

Três focos, no mesmo estilo mockado dos demais testes (AsyncMock, sem banco):

1. Importação sem IVA é rejeitada — coluna ausente e valor ausente por linha,
   com 0 sendo um valor válido (não "sem IVA").
2. Toda taxa importada nasce `pending` e não é faturável/ativável enquanto não
   houver aprovação manual (que ainda não existe — RBAC P2).
3. Cálculo EU só usa taxa `approved`; sem herança do IPI do grupo e sem zero
   de conveniência.
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

from app.api.routers.markets import (
    _parse_required_vat,
    activate_europe,
    import_europe_catalog,
)
from app.api.routers.orders import _resolve_eu_vat
from app.api.routers.auth import delete_my_account
from app.api.routers.users import delete_user
from app.schemas.auth import ReauthenticationRequest
from app.models.market import VAT_APPROVED, VAT_PENDING, VAT_REJECTED


ADMIN = SimpleNamespace(id=uuid.uuid4(), role="admin")


def _upload(csv_text: str) -> UploadFile:
    # Argumentos nomeados: compatível com a assinatura antiga e a nova do
    # Starlette (ordem posicional de `file`/`filename` mudou entre versões).
    return UploadFile(file=io.BytesIO(csv_text.encode("utf-8")), filename="europa.csv")


def _price_lists():
    return [
        SimpleNamespace(id=uuid.uuid4(), code=code, currency="EUR")
        for code in ("lojista", "corporativo", "pvp")
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


# ---------------------------------------------------------------------------
# 1. Importação sem IVA é rejeitada
# ---------------------------------------------------------------------------
class TestParseRequiredVat:
    def test_vazio_e_rejeitado(self):
        with pytest.raises(ValueError):
            _parse_required_vat("")

    def test_none_e_rejeitado(self):
        with pytest.raises(ValueError):
            _parse_required_vat(None)

    def test_zero_e_valido(self):
        # 0% é uma taxa explícita legítima (isento), não "sem IVA".
        assert _parse_required_vat("0") == Decimal("0")

    def test_taxa_normal(self):
        assert _parse_required_vat("23") == Decimal("23")

    def test_decimal_com_virgula(self):
        assert _parse_required_vat("23,5") == Decimal("23.5")

    def test_acima_de_cem_e_rejeitado(self):
        with pytest.raises(ValueError):
            _parse_required_vat("101")


def test_import_sem_coluna_vat_rate_rejeita_lote():
    async def run():
        # Cabeçalho sem vat_rate: rejeita antes de tocar o banco.
        csv_text = "product_code;lojista;corporativo;pvp\nEU-1;100;90;150\n"
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await import_europe_catalog(file=_upload(csv_text), db=db, _=ADMIN)
        assert exc.value.status_code == 422
        assert "vat_rate" in str(exc.value.detail)
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    asyncio.run(run())


def test_import_linha_sem_valor_de_vat_rejeita_lote():
    async def run():
        # Coluna presente, mas uma linha sem valor → lote inteiro rejeitado,
        # nada é gravado (nenhum commit).
        csv_text = (
            "product_code;lojista;corporativo;pvp;vat_rate\n"
            "EU-1;100;90;150;23\n"
            "EU-2;100;90;150;\n"
        )
        pid1, pid2 = uuid.uuid4(), uuid.uuid4()
        db = AsyncMock()
        db.execute.side_effect = [
            _AllResult([(pid1, "EU-1"), (pid2, "EU-2")]),
            _ScalarsResult(_price_lists()),
        ]
        with pytest.raises(HTTPException) as exc:
            await import_europe_catalog(file=_upload(csv_text), db=db, _=ADMIN)
        assert exc.value.status_code == 422
        db.commit.assert_not_called()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Taxa importada nasce pending e limpa aprovação anterior
# ---------------------------------------------------------------------------
def test_import_grava_pending_e_zera_aprovacao_sem_herdar_ipi():
    async def run():
        # Inclui a linha com 0 (válida) para provar que zero entra como taxa.
        csv_text = (
            "product_code;lojista;corporativo;pvp;vat_rate\n"
            "EU-1;100;90;150;23\n"
            "EU-2;100;90;150;0\n"
        )
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

        # Ambas as linhas importadas (0 é válido) e todas pendentes.
        assert result["imported"] == 2
        assert result["pending_vat_approval"] == 2
        assert "tax_rates_inherited_from_ilya" not in result

        # A busca de produtos não junta product_groups: sem herança do IPI.
        products_sql = str(statements[0])
        assert "product_groups" not in products_sql
        assert "products.market_code" in products_sql

        # Os upserts de product_markets gravam pending/import e limpam aprovação.
        inserts = [
            s for s in statements
            if getattr(getattr(s, "table", None), "name", None) == "product_markets"
        ]
        assert len(inserts) == 2
        for stmt in inserts:
            params = stmt.compile(dialect=postgresql.dialect()).params
            values = list(params.values())
            assert VAT_PENDING in values
            assert "import" in values  # VAT_SOURCE_IMPORT
            # approval zerada: nenhum status de aprovação é escrito
            assert VAT_APPROVED not in values

    asyncio.run(run())


def test_activate_recusa_eu_sem_iva_aprovado():
    async def run():
        # Três listas OK, mas há 1 SKU disponível sem IVA aprovado → 409.
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),                         # clientes fora de PT
            _CountResult(0),                         # representantes fora de PT
            _CountResult(0),                         # dimensões EU válidas
            _CountResult(1),                         # disponíveis
            _AllResult([(uuid.uuid4(), 3)]),         # com as 3 listas
            _CountResult(1),                         # sem IVA aprovado
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
            _CountResult(0),
        ]
        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)
        assert exc.value.status_code == 409
        assert "SKU" in exc.value.detail
        db.commit.assert_not_called()

    asyncio.run(run())


def test_activate_passa_quando_tudo_aprovado():
    async def run():
        market = SimpleNamespace(is_enabled=False)
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(0),
            _CountResult(0),
            _CountResult(0),
            _CountResult(1),                         # disponíveis
            _AllResult([(uuid.uuid4(), 3)]),         # com as 3 listas
            _CountResult(0),                         # nenhum sem IVA aprovado
        ]
        db.get = AsyncMock(return_value=market)

        result = await activate_europe(db=db, _=ADMIN)

        assert market.is_enabled is True
        assert result["enabled"] is True
        db.commit.assert_awaited_once()

    asyncio.run(run())


def test_activate_recusa_cadastro_eu_fora_de_portugal():
    async def run():
        db = AsyncMock()
        db.execute.side_effect = [
            _CountResult(1),  # cliente de outro país
            _CountResult(0),
        ]

        with pytest.raises(HTTPException) as exc:
            await activate_europe(db=db, _=ADMIN)

        assert exc.value.status_code == 409
        assert "PT" in exc.value.detail
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
# 3. Cálculo EU só usa taxa aprovada (sem herança, sem zero de conveniência)
# ---------------------------------------------------------------------------
class TestResolveEuVat:
    def test_aprovado_usa_a_taxa(self):
        assert _resolve_eu_vat("EU-1", Decimal("23.00"), VAT_APPROVED) == Decimal("23.00")

    def test_aprovado_aceita_zero(self):
        # Isenção aprovada (0%) é faturável; é diferente de taxa ausente.
        assert _resolve_eu_vat("EU-1", Decimal("0"), VAT_APPROVED) == Decimal("0")

    def test_pendente_e_recusado(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_eu_vat("EU-1", Decimal("23.00"), VAT_PENDING)
        assert exc.value.status_code == 422
        assert "EU-1" in exc.value.detail

    def test_rejeitado_e_recusado(self):
        with pytest.raises(HTTPException) as exc:
            _resolve_eu_vat("EU-1", Decimal("23.00"), VAT_REJECTED)
        assert exc.value.status_code == 422

    def test_aprovado_mas_sem_taxa_e_recusado(self):
        # Defesa em profundidade: o CHECK já impede, mas a rota não confia nisso.
        with pytest.raises(HTTPException) as exc:
            _resolve_eu_vat("EU-1", None, VAT_APPROVED)
        assert exc.value.status_code == 422


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
