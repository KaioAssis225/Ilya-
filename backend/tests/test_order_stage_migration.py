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


def test_client_registration_is_the_single_head_after_order_stage():
    script = _script()
    order_stage = script.get_revision("order_stage_r34")
    client_registration = script.get_revision("eu_client_registration_r35")
    assert order_stage is not None
    assert order_stage.down_revision == "eu_subgroups_br_r33"
    assert client_registration is not None
    assert client_registration.down_revision == "order_stage_r34"
    assert script.get_heads() == ["eu_client_registration_r35"]
