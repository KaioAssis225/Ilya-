"""Campos informativos do cadastro de clientes de Portugal."""

import pytest
from pydantic import ValidationError

from app.models.client import Client, anonymize_client_fields
from app.schemas.client import ClientCreate, ClientUpdate


BASE = {
    "name": "Casa Atlântico",
    "phone": "+351 912 345 678",
    "cep": "1000-001",
    "address": "Rua Um",
    "city": "Lisboa",
    "state": "--",
    "country": "PT",
}


def test_campos_informativos_sao_aceitos_sem_mudar_perfil_de_preco():
    client = ClientCreate(
        **BASE,
        contact_name="Maria Silva",
        client_type="arquiteto",
        observation="Contato após as 14h.",
    )

    assert client.contact_name == "Maria Silva"
    assert client.client_type == "arquiteto"
    assert client.observation == "Contato após as 14h."
    assert client.price_profile == "lojista"


def test_tipo_informativo_recusa_valor_desconhecido():
    with pytest.raises(ValidationError):
        ClientCreate(**BASE, client_type="revenda_inventada")


def test_campos_continuam_opcionais_para_cadastros_anteriores():
    client = ClientCreate(**BASE)
    assert client.contact_name is None
    assert client.client_type is None
    assert client.observation is None
    assert ClientUpdate(contact_name=None, client_type=None, observation=None)


def test_anonimizacao_remove_contato_e_observacao():
    client = Client(
        **BASE,
        contact_name="Maria Silva",
        client_type="arquiteto",
        observation="Falar com Maria após as 14h.",
    )

    anonymize_client_fields(client)

    assert client.contact_name is None
    assert client.observation is None
    # A classificação comercial não identifica uma pessoa e pode permanecer.
    assert client.client_type == "arquiteto"
