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


def test_free_country_iroko_is_the_single_head_after_vat_exempt():
    script = _script()
    order_stage = script.get_revision("order_stage_r34")
    client_registration = script.get_revision("eu_client_registration_r35")
    assert order_stage is not None
    assert order_stage.down_revision == "eu_subgroups_br_r33"
    assert client_registration is not None
    assert client_registration.down_revision == "order_stage_r34"
    vat_exempt = script.get_revision("order_vat_exempt_r36")
    assert vat_exempt is not None
    assert vat_exempt.down_revision == "eu_client_registration_r35"
    free_country_iroko = script.get_revision("eu_free_country_iroko_r37")
    assert free_country_iroko is not None
    assert free_country_iroko.down_revision == "order_vat_exempt_r36"
    special = script.get_revision("order_item_special_r38")
    assert special is not None
    assert special.down_revision == "eu_free_country_iroko_r37"
    contacted = script.get_revision("client_contacted_r39")
    assert contacted is not None
    assert contacted.down_revision == "order_item_special_r38"
    contacts = script.get_revision("client_contacts_r40")
    assert contacts is not None
    assert contacts.down_revision == "client_contacted_r39"
    assert script.get_heads() == ["client_contacts_r40"]
