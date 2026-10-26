"""Permissões de tabela de preço por representante e cliente (r23).

Testa a regra sem banco: escopo do dono, seleção do formulário e redação dos
preços no catálogo. O banco só entra no caminho de validação final, isolado
por um stub assíncrono.
"""
import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.price_access import (
    ensure_price_visible,
    owner_price_scope,
    resolve_price_selection,
    visible_price_scope,
)
from app.api.routers.clients import _price_selection
from app.api.routers.products import _to_read
from app.models.client import Client
from app.models.representative import Representative
from app.models.user import UserRole


def _product() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        product_code="ABC123",
        description="Poltrona Teste",
        type="Poltrona",
        is_circular=False,
        is_set=False,
        altura=Decimal("0.80"),
        largura=Decimal("1.20"),
        profundidade=Decimal("0.90"),
        price=Decimal("1000.00"),
        price_lojista=Decimal("1000.00"),
        custo_desativado=Decimal("1234.56"),
        price_corporativo=Decimal("1500.00"),
        observacao=None,
        all_optionals_categories=None,
        photo_path=None,
        optionals=[],
        set_items=[],
        components=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _user(role: UserRole, rep_id=None, linked_id=None) -> SimpleNamespace:
    return SimpleNamespace(role=role, rep_id=rep_id, linked_id=linked_id)


class _FakeScalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _FakeScalars(self._values)


class _FakeDb:
    def __init__(self, active_codes):
        self.active_codes = active_codes

    async def execute(self, statement):
        return _FakeResult(self.active_codes)


class TestOwnerPriceScope:
    def test_representante_com_todas_as_tabelas_nao_tem_escopo(self):
        rep = Representative(all_price_lists=True, price_list_codes=[])
        assert owner_price_scope(rep) is None

    def test_representante_restrito_usa_seus_codigos(self):
        rep = Representative(all_price_lists=False, price_list_codes=["pvp"])
        assert owner_price_scope(rep) == frozenset({"pvp"})

    def test_cliente_sem_listas_ve_so_perfil_de_faturamento(self):
        client = Client(
            all_price_lists=False,
            price_list_codes=[],
            price_profile="corporativo",
        )
        assert owner_price_scope(client) == frozenset({"corporativo"})

    def test_cliente_com_listas_soma_perfil_de_faturamento(self):
        client = Client(
            all_price_lists=False,
            price_list_codes=["pvp"],
            price_profile="lojista",
        )
        assert owner_price_scope(client) == frozenset({"pvp", "lojista"})


class TestVisiblePriceScope:
    def test_papeis_internos_veem_tudo_sem_consultar_banco(self):
        for role in (
            UserRole.admin,
            UserRole.vendedor,
            UserRole.cadastros,
            UserRole.produtos,
            UserRole.executivo,
            UserRole.benchmark_readonly,
        ):
            assert asyncio.run(visible_price_scope(None, _user(role), "BR")) is None


class TestResolvePriceSelection:
    def test_nada_informado_nao_mexe_na_permissao(self):
        assert asyncio.run(resolve_price_selection(
            None, "BR", all_price_lists=None, price_list_codes=None,
        )) is None

    def test_todas_as_tabelas_com_teto_e_403(self):
        with pytest.raises(HTTPException) as error:
            asyncio.run(resolve_price_selection(
                None, "BR",
                all_price_lists=True,
                price_list_codes=None,
                limit=frozenset({"lojista"}),
            ))
        assert error.value.status_code == 403

    def test_todas_as_tabelas_sem_teto_libera(self):
        assert asyncio.run(resolve_price_selection(
            None, "BR", all_price_lists=True, price_list_codes=None,
        )) == (True, ())

    def test_lista_vazia_sem_allow_empty_e_422(self):
        with pytest.raises(HTTPException) as error:
            asyncio.run(resolve_price_selection(
                None, "BR",
                all_price_lists=None,
                price_list_codes=[],
                allow_empty=False,
            ))
        assert error.value.status_code == 422

    def test_lista_vazia_com_allow_empty_nao_consulta_banco(self):
        assert asyncio.run(resolve_price_selection(
            None, "BR",
            all_price_lists=None,
            price_list_codes=[],
            allow_empty=True,
        )) == (False, ())

    def test_codigo_fora_do_teto_e_403(self):
        with pytest.raises(HTTPException) as error:
            asyncio.run(resolve_price_selection(
                None, "BR",
                all_price_lists=None,
                price_list_codes=["pvp"],
                limit=frozenset({"lojista"}),
            ))
        assert error.value.status_code == 403

    def test_codigos_duplicados_e_fora_de_ordem_sao_normalizados(self):
        fake_db = _FakeDb(["lojista", "corporativo"])
        result = asyncio.run(resolve_price_selection(
            fake_db, "BR",
            all_price_lists=None,
            price_list_codes=["corporativo", "lojista", "lojista"],
        ))
        assert result == (False, ("lojista", "corporativo"))


class TestPriceSelection:
    def test_representante_reenviando_todas_que_ja_ve_nao_mexe(self):
        user = SimpleNamespace(role=UserRole.representante)
        assert asyncio.run(_price_selection(
            None, "BR", user,
            all_price_lists=True,
            price_list_codes=None,
            limit=frozenset({"lojista"}),
            current=(True, ()),
        )) is None

    def test_representante_nao_pode_liberar_todas_quando_cliente_esta_restrito(self):
        user = SimpleNamespace(role=UserRole.representante)
        with pytest.raises(HTTPException) as error:
            asyncio.run(_price_selection(
                None, "BR", user,
                all_price_lists=True,
                price_list_codes=None,
                limit=frozenset({"lojista"}),
                current=(False, ()),
            ))
        assert error.value.status_code == 403


class TestEnsurePriceVisible:
    def test_bloqueia_tabela_fora_do_escopo(self):
        with pytest.raises(HTTPException) as error:
            ensure_price_visible(frozenset({"lojista"}), "corporativo")
        assert error.value.status_code == 403

    def test_escopo_total_nao_bloqueia(self):
        ensure_price_visible(None, "pvp")


class TestToReadPriceScope:
    def test_escopo_corporativo_esconde_lojista_e_coluna_legada(self):
        data = _to_read(_product(), frozenset({"corporativo"}))
        assert data.price_lojista is None
        assert data.price is None
        assert data.price_corporativo == Decimal("1500.00")

    def test_escopo_lojista_esconde_corporativo(self):
        data = _to_read(_product(), frozenset({"lojista"}))
        assert data.price_lojista == Decimal("1000.00")
        assert data.price_corporativo is None

    def test_escopo_total_mantem_os_dois_precos(self):
        data = _to_read(_product(), None)
        assert data.price_lojista == Decimal("1000.00")
        assert data.price_corporativo == Decimal("1500.00")
