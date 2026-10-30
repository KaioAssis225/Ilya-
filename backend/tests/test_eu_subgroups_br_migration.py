import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "eu_subgroups_br_migration",
    Path(__file__).parents[1] / "alembic/versions/eu_subgroups_br_r33_20261030.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_classifies_each_table_subgroup_without_confusing_rugs():
    assert migration.classify_eu_table_subgroup("IMJ0191", "ALBA - MESA DE JANTAR QUADRADA") == "MESA DE JANTAR"
    assert migration.classify_eu_table_subgroup("MC0373", "CIL - MESA DE CENTRO COM PUFF") == "MESA DE CENTRO"
    assert migration.classify_eu_table_subgroup("ML0250", "CERRADO - MESA LATERAL REDONDA") == "MESA LATERAL"
    assert migration.classify_eu_table_subgroup("MB0002", "MESA BISTRÔ REDONDA") == "MESA BISTRÔ"
    assert migration.classify_eu_table_subgroup(
        "AC0064", "TAPETE PARA MESA DE JANTAR", "TAPETES"
    ) is None


def test_classifies_high_and_low_stools_with_brazilian_names():
    assert migration.classify_eu_stool_subgroup("NEW HAVANA - ALTA BANQUETA COM BRAÇOS") == "BANQUETA ALTA"
    assert migration.classify_eu_stool_subgroup("MODO - BANQUETA BAIXA") == "BANQUETA BAIXA"
    assert migration.classify_eu_stool_subgroup("PARATY - BANCO RETANGULAR") is None
