"""Catálogo como dimensão independente de Grupo/Subgrupo.

Catálogo descreve a linha comercial (Ilya, IBTW, Cerâmica, Wupa, Tapete) e é
editável pelo usuário. Não se confunde com ProductGroup, que carrega o IPI:
por isso vive em tabela própria e filtra por id, sem cascata com o grupo.
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.catalog import CatalogCreate, CatalogUpdate
from app.schemas.product import ProductCreate, ProductUpdate


_CATALOG_ID = "3f1b2c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"


def _product_payload(**overrides):
    payload = {
        "catalog_id": _CATALOG_ID,
        "product_code": "CER0001",
        "description": "Vaso de teste",
        "type": "Vaso",
        "altura": Decimal("1"),
        "largura": Decimal("1"),
        "profundidade": Decimal("1"),
    }
    payload.update(overrides)
    return payload


def test_produto_exige_catalogo():
    # DEC-02 (catalog_permissions_r21): o catálogo define aba e permissão.
    payload = _product_payload()
    payload.pop("catalog_id")
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(payload)


def test_produto_aceita_catalogo():
    product = ProductCreate.model_validate(_product_payload())
    assert str(product.catalog_id) == _CATALOG_ID


def test_patch_nao_remove_catalogo():
    with pytest.raises(ValidationError):
        ProductUpdate.model_validate({"catalog_id": None})
    assert "catalog_id" not in ProductUpdate.model_validate({}).model_fields_set


def test_catalogo_exige_nome():
    with pytest.raises(ValidationError):
        CatalogCreate(name="")


def test_catalogo_limita_tamanho_do_nome():
    # Espelha String(50) do modelo: o banco truncaria/estouraria sem isso.
    with pytest.raises(ValidationError):
        CatalogCreate(name="c" * 51)


@pytest.mark.parametrize("nome", ["Ilya", "IBTW", "Cerâmica", "Wupa", "Tapete"])
def test_catalogos_iniciais_sao_validos(nome):
    assert CatalogCreate(name=nome).name == nome


def test_update_usa_as_mesmas_regras_do_create():
    assert CatalogUpdate(name="Cerâmica").name == "Cerâmica"
    with pytest.raises(ValidationError):
        CatalogUpdate(name="")


def test_update_altera_catalogo_do_produto():
    # ProductUpdate não herda de ProductBase: sem o campo declarado, editar um
    # produto descartaria o catálogo silenciosamente.
    from app.schemas.product import ProductUpdate

    catalog_id = "3f1b2c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    update = ProductUpdate.model_validate({"catalog_id": catalog_id})
    assert str(update.catalog_id) == catalog_id
    assert "catalog_id" in update.model_dump(exclude_unset=True)


def test_update_sem_catalogo_nao_mexe_no_campo():
    from app.schemas.product import ProductUpdate

    update = ProductUpdate.model_validate({"description": "Só a descrição"})
    assert "catalog_id" not in update.model_dump(exclude_unset=True)
