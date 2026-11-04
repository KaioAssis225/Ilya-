"""Limite de 20 m nas medidas de produto (mm digitado como metros: 470 em vez de 0,47)."""

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.api.routers.import_csv import import_products
from app.core.markets import MARKETS, MarketPrincipal
from app.core.product_dimensions import (
    MAX_PRODUCT_DIMENSION_M,
    PRODUCT_DIMENSION_LIMIT_MESSAGE,
    ensure_dimension_within_limit,
)
from app.models.user import UserRole
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductSetComponentCreate,
    ProductSetComponentRead,
    ProductUpdate,
)

pytestmark = pytest.mark.unit

DIMENSIONS = ("altura", "largura", "profundidade")


def _product_payload(**overrides):
    data = {
        "product_code": "CD0033",
        "description": "Cadeira",
        "catalog_id": uuid.uuid4(),
        "altura": "0.78",
        "largura": "0.47",
        "profundidade": "0.49",
    }
    data.update(overrides)
    return data


def _component_payload(**overrides):
    data = {"description": "Poltrona", "altura": "0.78", "largura": "0.47", "profundidade": "0.49"}
    data.update(overrides)
    return data


def test_limite_e_20_metros_e_a_mensagem_orienta_a_converter_mm():
    assert MAX_PRODUCT_DIMENSION_M == Decimal("20")
    assert "20 m" in PRODUCT_DIMENSION_LIMIT_MESSAGE
    assert "470 mm = 0,47" in PRODUCT_DIMENSION_LIMIT_MESSAGE


def test_ensure_dimension_within_limit_aceita_o_limite_e_none():
    assert ensure_dimension_within_limit(Decimal("20")) == Decimal("20")
    assert ensure_dimension_within_limit(Decimal("0.47")) == Decimal("0.47")
    assert ensure_dimension_within_limit(None) is None
    with pytest.raises(ValueError, match="Medida acima de 20 m"):
        ensure_dimension_within_limit(Decimal("20.01"))


@pytest.mark.parametrize("field", DIMENSIONS)
@pytest.mark.parametrize("value", ["20", "20.00", "0.47", "0"])
def test_schemas_de_escrita_aceitam_ate_20_metros(field, value):
    ProductCreate(**_product_payload(**{field: value}))
    ProductUpdate(**{field: value})
    ProductSetComponentCreate(**_component_payload(**{field: value}))


@pytest.mark.parametrize("field", DIMENSIONS)
@pytest.mark.parametrize("value", ["20.01", "470", "780"])
def test_schemas_de_escrita_recusam_acima_de_20_metros(field, value):
    for build in (
        lambda: ProductCreate(**_product_payload(**{field: value})),
        lambda: ProductUpdate(**{field: value}),
        lambda: ProductSetComponentCreate(**_component_payload(**{field: value})),
    ):
        with pytest.raises(ValidationError) as exc:
            build()
        assert PRODUCT_DIMENSION_LIMIT_MESSAGE in str(exc.value)


def test_update_sem_medidas_nao_valida_nada():
    assert ProductUpdate().altura is None


def test_componente_acima_do_limite_recusa_o_produto_conjunto():
    with pytest.raises(ValidationError) as exc:
        ProductCreate(**_product_payload(is_set=True, components=[_component_payload(largura="470")]))
    assert PRODUCT_DIMENSION_LIMIT_MESSAGE in str(exc.value)


def test_leitura_nao_quebra_com_produto_ja_gravado_em_mm():
    # CD0033 está no banco com 470/490/780; a API precisa continuar lendo.
    now = "2026-01-01T00:00:00Z"
    product = ProductRead(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        **_product_payload(altura="780", largura="470", profundidade="490"),
    )
    assert product.largura == Decimal("470")
    component = ProductSetComponentRead(
        id=uuid.uuid4(), description="Poltrona", is_circular=False,
        altura=Decimal("780"), largura=Decimal("470"), profundidade=Decimal("490"), qty=1,
    )
    assert component.altura == Decimal("780")


def _principal() -> MarketPrincipal:
    return MarketPrincipal(
        user=SimpleNamespace(id=uuid.uuid4()),
        market=MARKETS["BR"],
        access=SimpleNamespace(role=UserRole.admin.value),
    )


def _run_import(rows):
    """Roda import_products com banco e carregamentos mockados; devolve o resumo."""

    async def run():
        db = AsyncMock()
        db.add = MagicMock()
        # Um mesmo resultado serve ao catálogo (name/id) e às listas de preço (code/id).
        catalog_and_lists = [
            SimpleNamespace(name="Ilya", code="lojista", id=uuid.uuid4()),
            SimpleNamespace(name="Ilya corp", code="corporativo", id=uuid.uuid4()),
        ]
        result = MagicMock()
        result.scalars.return_value.all.return_value = catalog_and_lists
        db.execute = AsyncMock(return_value=result)
        with (
            patch("app.api.routers.import_csv._load_rows", AsyncMock(return_value=rows)),
            patch("app.api.routers.import_csv._acquire_import_lock", AsyncMock()),
            patch(
                "app.api.routers.import_csv._load_chunked",
                AsyncMock(side_effect=[[], [SimpleNamespace(name="Outro")]]),
            ),
            patch(
                "app.api.routers.import_csv.product_type_fiscal_snapshot",
                AsyncMock(return_value=(None, None)),
            ),
            patch("app.api.routers.import_csv.record_product_fiscal_assignment", MagicMock()),
            patch("app.api.routers.import_csv._finalize", AsyncMock(return_value=True)),
        ):
            return await import_products(
                file=SimpleNamespace(), db=db, current_user=None, principal=_principal(),
            )

    return asyncio.run(run())


def _csv_row(**overrides):
    row = {
        # O leitor de CSV normaliza cabeçalhos (sem "_" nem caixa): "product_code" → "productcode".
        "productcode": "P1",
        "description": "Cadeira",
        "catalogo": "Ilya",
        "pricelojista": "100",
        "pricecorporativo": "90",
        "altura": "0,78",
        "largura": "0,47",
        "profundidade": "0,49",
    }
    row.update(overrides)
    return row


def test_csv_aceita_medida_exatamente_no_limite():
    result = _run_import([_csv_row(largura="20", altura="20,00", profundidade="20")])
    assert result["errors"] == []
    assert result["created"] == 1


@pytest.mark.parametrize("field", DIMENSIONS)
@pytest.mark.parametrize("value", ["20,01", "470"])
def test_csv_linha_acima_do_limite_vira_erro_da_linha(field, value):
    result = _run_import([_csv_row(), _csv_row(productcode="P2", **{field: value})])
    assert result["errors"] == [{"row": 3, "message": PRODUCT_DIMENSION_LIMIT_MESSAGE}]


def test_csv_profundidade_de_produto_circular_e_ignorada():
    result = _run_import([_csv_row(iscircular="sim", profundidade="470")])
    assert result["errors"] == []
