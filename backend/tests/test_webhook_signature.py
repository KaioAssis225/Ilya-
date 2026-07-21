"""Testes da assinatura HMAC dos webhooks de integracao (Ilya -> Ilya Estoque).

O foco e o contrato de bytes: a assinatura cobre o corpo EXATO que trafega.
Se um dia alguem "melhorar" o modulo re-serializando JSON, estes testes quebram
antes de a integracao quebrar em producao.
"""
import json

import pytest

from app.core import webhook_signature as ws


SECRET = "segredo-de-teste"
BODY = b'{"event_id":"2f81f0af-6a47-4e59-bf60-1506123ce934","event_type":"test.ping"}'
TS = "1784739000"


def test_assinatura_e_estavel_para_o_mesmo_corpo():
    assert ws.sign(SECRET, TS, BODY) == ws.sign(SECRET, TS, BODY)


def test_assinatura_confere():
    assert ws.verify(SECRET, TS, BODY, ws.sign(SECRET, TS, BODY)) is True


def test_segredo_errado_nao_confere():
    assinatura = ws.sign(SECRET, TS, BODY)
    assert ws.verify("outro-segredo", TS, BODY, assinatura) is False


def test_corpo_alterado_invalida_assinatura():
    assinatura = ws.sign(SECRET, TS, BODY)
    assert ws.verify(SECRET, TS, BODY + b" ", assinatura) is False


def test_timestamp_alterado_invalida_assinatura():
    """O timestamp entra no payload assinado, entao trocar so ele quebra."""
    assinatura = ws.sign(SECRET, TS, BODY)
    assert ws.verify(SECRET, "1784739001", BODY, assinatura) is False


def test_reserializar_json_quebra_a_assinatura():
    """Documenta a armadilha nº 1 de webhooks.

    Desserializar e re-serializar produz bytes diferentes (espacamento), logo
    assinatura diferente. O receptor PRECISA usar o corpo cru.
    """
    reserializado = json.dumps(json.loads(BODY)).encode("utf-8")
    assert reserializado != BODY
    assert ws.verify(SECRET, TS, reserializado, ws.sign(SECRET, TS, BODY)) is False


def test_assinatura_vazia_nao_confere():
    assert ws.verify(SECRET, TS, BODY, "") is False


def test_recusa_assinar_sem_segredo():
    with pytest.raises(ValueError):
        ws.sign("", TS, BODY)


def test_timestamp_atual_e_fresco():
    assert ws.timestamp_is_fresh(ws.current_timestamp()) is True


def test_timestamp_antigo_e_rejeitado():
    antigo = str(int(ws.current_timestamp()) - ws.MAX_TIMESTAMP_SKEW_SECONDS - 1)
    assert ws.timestamp_is_fresh(antigo) is False


def test_timestamp_invalido_e_rejeitado():
    assert ws.timestamp_is_fresh("nao-e-numero") is False


def test_build_headers_produz_assinatura_conferivel():
    event_id = "2f81f0af-6a47-4e59-bf60-1506123ce934"
    headers = ws.build_headers(SECRET, event_id, BODY)

    assert headers[ws.HEADER_EVENT_ID] == event_id
    assert headers["Content-Type"] == "application/json"
    assert ws.timestamp_is_fresh(headers[ws.HEADER_TIMESTAMP]) is True
    assert ws.verify(
        SECRET, headers[ws.HEADER_TIMESTAMP], BODY, headers[ws.HEADER_SIGNATURE]
    ) is True
