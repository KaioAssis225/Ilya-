"""Testes do worker de entrega da Outbox (Ilya -> Ilya Estoque).

Nao tocam banco nem rede: a linha da outbox e mockada com SimpleNamespace e o
cliente HTTP e um duble. O alvo e a maquina de estados — classificacao de
resposta, escada de retentativas e dead_letter — que e onde mora o risco real.
"""
import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.services.integration_events import build_envelope, serialize_envelope
from app.workers import webhook_sender as w


def _run(coro):
    """Executa a corrotina sem depender de plugin async do pytest.

    O projeto so tem `pytest` nas dependencias; usar @pytest.mark.asyncio sem
    o pytest-asyncio faria o teste ser PULADO em silencio — que e pior do que
    nao existir, porque parece verde.
    """
    return asyncio.run(coro)


def _row(attempts: int = 0) -> SimpleNamespace:
    envelope = build_envelope("test.ping", {"ok": True})
    return SimpleNamespace(
        event_id=uuid.uuid4(),
        event_type="test.ping",
        payload=envelope,
        status="pending",
        attempts=attempts,
        next_attempt_at=None,
        last_error=None,
        delivered_at=None,
    )


class _FakeClient:
    """Duble do httpx.AsyncClient: devolve resposta fixa ou levanta erro."""

    def __init__(self, *, status_code=None, headers=None, exc=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.exc = exc
        self.calls = []

    async def post(self, url, content=None, headers=None, timeout=None):
        self.calls.append({"url": url, "content": content, "headers": headers})
        if self.exc:
            raise self.exc
        return httpx.Response(
            status_code=self.status_code,
            headers=self.headers,
            text="detalhe",
            request=httpx.Request("POST", url or "http://x"),
        )


# ── classificacao de resposta (secao 11 do contrato) ─────────────────────────

@pytest.mark.parametrize("code", [200, 201, 202, 204])
def test_2xx_e_entrega(code):
    assert w.classify_response(code) == w.DELIVERED


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_sobrecarga_e_falha_temporaria_sao_retentaveis(code):
    assert w.classify_response(code) == w.RETRY


@pytest.mark.parametrize("code", [400, 401, 403, 409, 422])
def test_erros_de_contrato_e_permissao_vao_para_analise(code):
    """Repetir um 400 ou 401 nao muda o resultado — so gera ruido."""
    assert w.classify_response(code) == w.DEAD_LETTER


# ── escada de retentativas ───────────────────────────────────────────────────

def test_escada_segue_a_ordem_do_contrato():
    assert w.RETRY_DELAYS_SECONDS == (60, 300, 900, 3600, 21600, 86400)


def test_primeira_falha_espera_um_minuto():
    assert w.next_delay_seconds(1) == 60


def test_escada_progride():
    assert [w.next_delay_seconds(n) for n in range(1, 7)] == [
        60, 300, 900, 3600, 21600, 86400
    ]


def test_escada_esgotada_devolve_none():
    assert w.next_delay_seconds(len(w.RETRY_DELAYS_SECONDS) + 1) is None


# ── entrega ──────────────────────────────────────────────────────────────────

def test_sucesso_marca_entregue(monkeypatch):
    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    row = _row()

    _run(w.deliver_one(_FakeClient(status_code=202), row))

    assert row.status == "delivered"
    assert row.attempts == 1
    assert row.delivered_at is not None
    assert row.last_error is None


def test_falha_de_rede_reagenda(monkeypatch):
    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_MAX_ATTEMPTS", 7, raising=False)
    row = _row()

    _run(w.deliver_one(_FakeClient(exc=httpx.ConnectError("sem rota")), row))

    assert row.status == "pending"
    assert row.attempts == 1
    assert row.next_attempt_at is not None
    assert "ConnectError" in row.last_error


def test_erro_de_contrato_vai_para_dead_letter(monkeypatch):
    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    row = _row()

    _run(w.deliver_one(_FakeClient(status_code=400), row))

    assert row.status == "dead_letter"
    assert "HTTP 400" in row.last_error


def test_tentativas_esgotadas_viram_dead_letter(monkeypatch):
    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_MAX_ATTEMPTS", 3, raising=False)
    row = _row(attempts=2)

    _run(w.deliver_one(_FakeClient(status_code=503), row))

    assert row.attempts == 3
    assert row.status == "dead_letter"


def test_429_respeita_retry_after(monkeypatch):
    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_MAX_ATTEMPTS", 7, raising=False)
    row = _row()

    client = _FakeClient(status_code=429, headers={"Retry-After": "120"})
    _run(w.deliver_one(client, row))

    assert row.status == "pending"
    # Reagendou pelo Retry-After (120s), nao pelos 60s da escada.
    assert row.next_attempt_at is not None


def test_corpo_enviado_bate_com_a_assinatura(monkeypatch):
    """O que e assinado tem de ser exatamente o que trafega."""
    from app.core import webhook_signature as ws

    monkeypatch.setattr(w.settings, "WEBHOOK_SECRET", "segredo", raising=False)
    monkeypatch.setattr(w.settings, "WEBHOOK_URL", "http://receptor/hook", raising=False)
    row = _row()
    client = _FakeClient(status_code=200)

    _run(w.deliver_one(client, row))

    enviado = client.calls[0]
    corpo = enviado["content"]
    cabecalhos = enviado["headers"]

    assert corpo == serialize_envelope(row.payload)
    assert ws.verify(
        "segredo",
        cabecalhos[ws.HEADER_TIMESTAMP],
        corpo,
        cabecalhos[ws.HEADER_SIGNATURE],
    ) is True
    assert cabecalhos[ws.HEADER_EVENT_ID] == str(row.event_id)


def test_erro_e_truncado_e_achatado():
    longo = "linha1\n" + ("x" * 900)
    resumido = w._truncate_error(longo)
    assert len(resumido) <= 500
    assert "\n" not in resumido


def test_serializacao_e_deterministica():
    """Retentativas precisam produzir bytes identicos."""
    envelope = build_envelope("test.ping", {"b": 2, "a": 1})
    assert serialize_envelope(envelope) == serialize_envelope(envelope)
