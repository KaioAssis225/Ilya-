"""Bloco 96: visibilidade de preço no catálogo por permissão.

A regra é que o preço que a role logada não pode ver nem sai da API — não basta
esconder na tela. Estes testes travam esse contrato sem depender de banco:
`_visible_price_profile` decide qual tabela cada conta enxerga e `_to_read`
aplica a decisão no payload.
"""
import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.api.routers.products import _to_read, _visible_price_profile
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


def _user(role: UserRole, linked_id=None) -> SimpleNamespace:
    # linked_id é o que is_client_account() usa para reconhecer conta legada (SEC-01).
    return SimpleNamespace(role=role, linked_id=linked_id)


class TestVisiblePriceProfile:
    def test_operador_interno_e_representante_veem_as_duas_tabelas(self):
        for role in (UserRole.admin, UserRole.vendedor, UserRole.produtos,
                     UserRole.cadastros, UserRole.representante, UserRole.executivo):
            # db=None prova que nem chega a consultar o banco para essas roles.
            assert asyncio.run(_visible_price_profile(None, _user(role))) is None

    def test_conta_cliente_sem_vinculo_cai_para_lojista(self):
        user = _user(UserRole.cliente, linked_id=None)
        assert asyncio.run(_visible_price_profile(None, user)) == "lojista"


class TestToReadRedaction:
    def test_custo_desativado_nunca_integra_payload_da_api(self):
        data = _to_read(_product(), None)
        assert "custo_desativado" not in data.model_dump()

    def test_sem_perfil_definido_mantem_os_dois_precos(self):
        data = _to_read(_product(), None)
        assert data.price_lojista == Decimal("1000.00")
        assert data.price_corporativo == Decimal("1500.00")

    def test_cliente_lojista_nao_recebe_preco_corporativo(self):
        data = _to_read(_product(), "lojista")
        assert data.price_lojista == Decimal("1000.00")
        assert data.price_corporativo is None

    def test_cliente_corporativo_nao_recebe_preco_lojista(self):
        data = _to_read(_product(), "corporativo")
        assert data.price_corporativo == Decimal("1500.00")
        assert data.price_lojista is None
        # A coluna legada `price` espelha o preço lojista (Bloco 62) e por isso
        # também precisa sumir, senão vazaria o valor pela porta dos fundos.
        assert data.price is None
