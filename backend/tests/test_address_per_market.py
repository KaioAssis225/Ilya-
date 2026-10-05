"""Endereço por mercado: sentinela de UF e sigla oficial.

Dois achados do Bloco 06:

1. **Importação EU era impossível.** `_uf` exigia sempre duas letras, sem olhar
   o mercado, então nenhuma linha do CSV europeu passava — um cliente português
   não tem UF para informar. O cadastro pela API já resolvia com a sentinela
   `--`; a importação não.
2. **UF inexistente era aceita.** A `CheckConstraint ck_clients_state_uf` valida
   só o formato (`^[A-Z]{2}$`), então `XX` entrava no banco pela API e pelo CSV.
"""

import pytest
from pydantic import ValidationError

from app.api.routers.import_csv import _address_fields, _uf
from app.core.addresses import BR_STATES, UF_SENTINEL, is_valid_uf
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.representative import RepresentativeCreate


def _row(**kw):
    base = {
        "name": "Cliente",
        "phone": "1999999999",
        "cep": "13340600",
        "address": "Rodovia Engenheiro Ermenio de Oliveira Penteado",
        "city": "Indaiatuba",
    }
    base.update(kw)
    return base


# --- lista oficial ---------------------------------------------------------

def test_lista_de_ufs_tem_as_27_siglas():
    assert len(BR_STATES) == 27
    for sigla in ("SP", "RJ", "DF", "TO", "AC"):
        assert is_valid_uf(sigla)
    for invalida in ("XX", "ZZ", "SPX", "s", "", UF_SENTINEL):
        assert not is_valid_uf(invalida)


# --- importação: UF conforme o mercado ------------------------------------

def test_import_br_exige_uf_e_recusa_sigla_inexistente():
    assert _uf(_row(state="sp"), "BR") == "SP"
    with pytest.raises(ValueError, match="UF inválida"):
        _uf(_row(state="XX"), "BR")
    with pytest.raises(ValueError, match="obrigatória"):
        _uf(_row(state=""), "BR")
    with pytest.raises(ValueError, match="obrigatória"):
        _uf(_row(state=UF_SENTINEL), "BR")


def test_import_eu_aceita_coluna_vazia_com_a_sentinela():
    """Era o bug: a linha europeia morria em `_uf` antes de chegar ao banco."""
    assert _uf(_row(state=""), "EU") == UF_SENTINEL
    assert _uf(_row(), "EU") == UF_SENTINEL
    assert _uf(_row(state=UF_SENTINEL), "EU") == UF_SENTINEL


def test_import_eu_recusa_uf_preenchida_e_aponta_region():
    with pytest.raises(ValueError, match="não se aplica"):
        _uf(_row(state="SP"), "EU")


def test_address_fields_propaga_o_mercado():
    """O default é BR para não mudar o comportamento de quem chama sem mercado,
    mas os dois importadores passam `principal.code` explicitamente."""
    assert _address_fields(_row(state="MG"))["state"] == "MG"
    assert _address_fields(_row(state="MG"), "BR")["state"] == "MG"
    assert _address_fields(_row(state=""), "EU")["state"] == UF_SENTINEL


# --- cadastro pela API ----------------------------------------------------

def test_cadastro_recusa_uf_inexistente():
    with pytest.raises(ValidationError):
        ClientCreate(**_row(state="XX"))
    with pytest.raises(ValidationError):
        RepresentativeCreate(**_row(state="XX"))
    with pytest.raises(ValidationError):
        ClientUpdate(state="XX")


def test_cadastro_normaliza_e_aceita_sigla_oficial():
    assert ClientCreate(**_row(state="sp")).state == "SP"
    assert ClientCreate(**_row(state=" rj ")).state == "RJ"
    assert RepresentativeCreate(**_row(state="mg")).state == "MG"
    assert ClientUpdate(state="df").state == "DF"


def test_cadastro_sem_uf_usa_a_sentinela_para_mercado_sem_estado():
    """O default do schema é a sentinela: ela atravessa o `NOT NULL` da coluna,
    e o handler de `POST /clients` a recusa quando o mercado é BR."""
    assert ClientCreate(**_row()).state == UF_SENTINEL
    assert ClientCreate(**_row(state=UF_SENTINEL)).state == UF_SENTINEL
    assert ClientUpdate(state=UF_SENTINEL).state == UF_SENTINEL
    assert ClientUpdate(state=None).state is None
