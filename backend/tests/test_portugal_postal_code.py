"""Código postal português preenche a morada (rua) e não só a localidade.

Regressão: a consulta usava só o zippopotam.us, que para Portugal devolve
localidade e distrito mas nunca a rua — o cadastro EU ficava com "Endereço"
vazio, ao contrário do CEP brasileiro. A fonte principal passa a ser o
GeoAPI.pt (dados CTT/INE), com o zippopotam como reserva.
"""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.api.routers import utils

GEOAPI_1000_001 = {
    "CP": "1000-001",
    "Distrito": "Lisboa",
    "Concelho": "Lisboa",
    "Localidade": "Lisboa",
    "Designação Postal": "LISBOA",
    "partes": [{"Artéria": "Rua dos Açores", "Local": "", "Troço": "Impares de 1 a 19", "Porta": "", "Cliente": ""}],
    "ruas": ["R AÇORES"],
}

ZIPPO_1000_001 = {
    "post code": "1000-001",
    "places": [{"place name": "Lisboa", "state": "Lisboa"}],
}


def _client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        for host, response in routes.items():
            if request.url.host == host:
                return response
        raise AssertionError(f"host inesperado: {request.url.host}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _lookup(monkeypatch, routes: dict[str, httpx.Response]) -> dict:
    monkeypatch.setattr(utils, "external_http_client", _client(routes))
    return asyncio.run(utils.lookup_portugal_address("1000-001"))


def test_parser_geoapi_traz_rua_localidade_e_distrito():
    assert utils.portugal_address_from_geoapi(GEOAPI_1000_001) == {
        "logradouro": "Rua dos Açores",
        "bairro": "",
        "localidade": "Lisboa",
        "uf": "--",
        "regiao": "Lisboa",
    }


def test_parser_geoapi_sem_partes_usa_lista_de_ruas():
    data = {**GEOAPI_1000_001, "partes": []}
    assert utils.portugal_address_from_geoapi(data)["logradouro"] == "R AÇORES"


def test_lookup_usa_geoapi_quando_disponivel(monkeypatch):
    result = _lookup(monkeypatch, {"json.geoapi.pt": httpx.Response(200, json=GEOAPI_1000_001)})
    assert result["logradouro"] == "Rua dos Açores"
    assert result["localidade"] == "Lisboa"


def test_lookup_cai_para_zippopotam_se_geoapi_falhar(monkeypatch):
    result = _lookup(monkeypatch, {
        "json.geoapi.pt": httpx.Response(503),
        "api.zippopotam.us": httpx.Response(200, json=ZIPPO_1000_001),
    })
    assert result["localidade"] == "Lisboa"
    assert result["regiao"] == "Lisboa"
    assert result["logradouro"] == ""


def test_lookup_404_nas_duas_fontes_responde_nao_encontrado(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _lookup(monkeypatch, {
            "json.geoapi.pt": httpx.Response(404),
            "api.zippopotam.us": httpx.Response(404),
        })
    assert exc.value.status_code == 404
