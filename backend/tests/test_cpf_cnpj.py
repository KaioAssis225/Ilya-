"""CPF/CNPJ nos cadastros de cliente e representante.

Os documentos aqui são sintéticos: foram escolhidos porque o dígito
verificador fecha, não porque pertençam a alguém.
"""
import uuid

import pytest
from pydantic import ValidationError

from app.api.routers.import_csv import _address_fields
from app.core.documents import format_cpf_cnpj, normalize_cpf_cnpj
from app.models.client import Client, anonymize_client_fields
from app.models.representative import Representative, anonymize_representative_fields
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate
from app.schemas.representative import RepresentativeCreate, RepresentativeUpdate

VALID_CPF = "52998224725"
VALID_CNPJ = "11222333000181"

_ADDRESS = {
    "name": "Fulano",
    "phone": "(11) 90000-0000",
    "cep": "01001-000",
    "address": "Rua Um",
    "city": "São Paulo",
    "state": "SP",
}


class TestNormalizacao:
    def test_aceita_com_e_sem_mascara_e_guarda_so_digitos(self):
        # Duas grafias do mesmo documento têm de colidir no índice único.
        assert normalize_cpf_cnpj("529.982.247-25") == VALID_CPF
        assert normalize_cpf_cnpj(VALID_CPF) == VALID_CPF
        assert normalize_cpf_cnpj("11.222.333/0001-81") == VALID_CNPJ

    def test_digito_verificador_errado_e_recusado(self):
        with pytest.raises(ValueError, match="dígito verificador"):
            normalize_cpf_cnpj("52998224724")
        with pytest.raises(ValueError, match="dígito verificador"):
            normalize_cpf_cnpj("11222333000182")

    def test_digitos_repetidos_sao_recusados(self):
        # 111.111.111-11 fecha a conta do DV; só a checagem de repetição pega.
        with pytest.raises(ValueError, match="repetidos"):
            normalize_cpf_cnpj("11111111111")
        with pytest.raises(ValueError, match="repetidos"):
            normalize_cpf_cnpj("00000000000000")

    def test_comprimento_fora_de_11_ou_14(self):
        with pytest.raises(ValueError, match="11 ou 14"):
            normalize_cpf_cnpj("529982247")

    def test_vazio_e_tipo_errado(self):
        with pytest.raises(ValueError, match="obrigatório"):
            normalize_cpf_cnpj("---")
        with pytest.raises(ValueError, match="texto"):
            normalize_cpf_cnpj(52998224725)

    def test_formatacao_para_exibicao(self):
        assert format_cpf_cnpj(VALID_CPF) == "529.982.247-25"
        assert format_cpf_cnpj(VALID_CNPJ) == "11.222.333/0001-81"
        assert format_cpf_cnpj(None) is None


class TestCadastroAceitaDocumento:
    def test_cliente_novo_sem_documento_e_valido(self):
        # Opcional por decisão de produto: cadastro de feira não trava.
        assert ClientCreate(**_ADDRESS).cpf_cnpj is None

    def test_representante_novo_sem_documento_e_valido(self):
        assert RepresentativeCreate(**_ADDRESS).cpf_cnpj is None

    def test_documento_chega_normalizado_ao_modelo(self):
        payload = ClientCreate(**_ADDRESS, cpf_cnpj="529.982.247-25")
        assert payload.cpf_cnpj == VALID_CPF
        rep = RepresentativeCreate(**_ADDRESS, cpf_cnpj="11.222.333/0001-81")
        assert rep.cpf_cnpj == VALID_CNPJ

    def test_documento_invalido_no_cadastro_vira_422(self):
        with pytest.raises(ValidationError):
            ClientCreate(**_ADDRESS, cpf_cnpj="11111111111")


class TestLeituraEEdicao:
    def test_cadastro_sem_documento_continua_legivel(self):
        # A coluna aceita nulo; se ClientRead exigisse o campo, ler qualquer
        # cadastro sem documento passaria a estourar 500.
        read = ClientRead(
            **_ADDRESS,
            id=uuid.uuid4(),
            created_at="2026-08-10T00:00:00Z",
            updated_at="2026-08-10T00:00:00Z",
            last_activity_at="2026-08-10T00:00:00Z",
        )
        assert read.cpf_cnpj is None

    def test_edicao_sem_o_campo_nao_mexe_no_documento(self):
        update = ClientUpdate(city="Campinas")
        assert "cpf_cnpj" not in update.model_dump(exclude_unset=True)

    def test_edicao_pode_limpar_o_documento(self):
        # Campo opcional: mandar vazio apaga em vez de estourar 422.
        assert ClientUpdate(cpf_cnpj=None).cpf_cnpj is None
        assert RepresentativeUpdate(cpf_cnpj="").cpf_cnpj is None

    def test_edicao_recusa_documento_invalido(self):
        with pytest.raises(ValidationError):
            ClientUpdate(cpf_cnpj="52998224724")

    def test_edicao_normaliza_documento_novo(self):
        assert ClientUpdate(cpf_cnpj="529.982.247-25").cpf_cnpj == VALID_CPF


class TestImportacaoCsv:
    _ROW = {
        "name": "Sem documento",
        "phone": "(11) 99999-9999",
        "cep": "01001-000",
        "address": "Praça da Sé",
        "city": "São Paulo",
        "state": "SP",
    }

    def test_linha_sem_documento_e_aceita(self):
        assert _address_fields(dict(self._ROW))["cpf_cnpj"] is None

    def test_documento_da_planilha_chega_normalizado(self):
        # 'cpf' e não 'cpf_cnpj': _read_rows tira o sublinhado do cabeçalho.
        row = {**self._ROW, "cpf": "529.982.247-25"}
        assert _address_fields(row)["cpf_cnpj"] == VALID_CPF

    def test_documento_invalido_na_planilha_para_a_linha(self):
        with pytest.raises(ValueError, match="dígito verificador"):
            _address_fields({**self._ROW, "cnpj": "11222333000182"})


class TestAnonimizacao:
    def test_anonimizar_cliente_remove_o_documento(self):
        client = Client(id=uuid.uuid4(), cpf_cnpj=VALID_CPF, **_ADDRESS)
        anonymize_client_fields(client)
        assert client.cpf_cnpj is None

    def test_anonimizar_representante_remove_o_documento(self):
        rep = Representative(id=uuid.uuid4(), cpf_cnpj=VALID_CNPJ, **_ADDRESS)
        anonymize_representative_fields(rep)
        assert rep.cpf_cnpj is None
