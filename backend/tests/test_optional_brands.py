"""Approved list, validation and default for clients that predate brand selection."""
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.optional import OptionalColorCreate, OptionalColorUpdate

spec = importlib.util.spec_from_file_location("optional_brands_migration", Path(__file__).parents[1] / "alembic/versions/optional_brands_r25_20261026.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_approved_brand_reference_does_not_confuse_shared_colors_or_woods():
    assert migration.is_ibtw("ALUMINIO_IBTW", "AREIA")
    assert not migration.is_ibtw("ALUMÍNIO", "AREIA")
    assert migration.is_ibtw("TECIDOS_IBTW", "PANAMÁ BAUNILHA  / NEVOA")
    assert migration.is_ibtw("MADEIRA", "IROKO NATURAL ÓLEO")
    assert not migration.is_ibtw("MADEIRA", "IROKO CARVÃO ÓLEO")
    assert not migration.is_ibtw("MADEIRA", "IROKO PATINA ÓLEO")
    assert not migration.is_ibtw("TEKA", "POLYWOOD")
    assert migration.is_ibtw("CERAMICA_ARTESANAL", "AREIA MESCLA")
    assert not migration.is_ibtw("CERAMICA_ARTESANAL", "OUTRA COR")


def test_brand_validation_and_legacy_default():
    assert OptionalColorCreate(category="MADEIRA", color_name="Cor").brand == "ILYA"
    assert OptionalColorCreate(category="MADEIRA", color_name="Cor", brand="IBTW").brand == "IBTW"
    assert OptionalColorUpdate(color_name="Cor").model_dump(exclude_unset=True) == {"color_name": "Cor"}
    for invalid in [None, "", "EU", "OUTRA"]:
        with pytest.raises(ValidationError):
            OptionalColorUpdate(brand=invalid)
