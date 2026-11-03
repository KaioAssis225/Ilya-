"""Cadeia da migration da etapa do pedido: uma única head, encadeada à anterior."""
import warnings
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND = Path(__file__).parents[1]


def _script() -> ScriptDirectory:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    with warnings.catch_warnings():
        # O alembic.ini do projeto não define path_separator (aviso do próprio Alembic).
        warnings.simplefilter("ignore", DeprecationWarning)
        return ScriptDirectory.from_config(config)


def test_order_stage_migration_is_the_single_head_after_subgroups():
    script = _script()
    revision = script.get_revision("order_stage_r34")
    assert revision is not None
    assert revision.down_revision == "eu_subgroups_br_r33"
    assert script.get_heads() == ["order_stage_r34"]
