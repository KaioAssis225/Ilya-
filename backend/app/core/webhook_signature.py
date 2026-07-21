"""Assinatura HMAC-SHA256 dos webhooks de integração.

Contrato (seção 8 do PLANEJAMENTO-WEBHOOK-ILYA-ESTOQUE):

    assinatura = HMAC-SHA256(segredo, timestamp + "." + corpo_original)

O ponto crítico é `corpo_original`: a assinatura é calculada sobre os BYTES
exatos que trafegam. Se qualquer lado desserializar o JSON e re-serializar
antes de conferir, a assinatura não bate — a ordem das chaves ou o espaçamento
mudam. É a causa nº 1 de falha em integração por webhook, e por isso este
módulo trabalha com `bytes` e nunca com `dict`.

O receptor (Ilya Estoque, em Cloudflare Workers) implementa o mesmo algoritmo
com Web Crypto, já que Workers não expõem o módulo `crypto` do Node.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

# Cabeçalhos do contrato.
HEADER_EVENT_ID = "X-Ilya-Event-Id"
HEADER_TIMESTAMP = "X-Ilya-Timestamp"
HEADER_SIGNATURE = "X-Ilya-Signature"

# Janela de tolerância para o timestamp. Protege contra replay de mensagens
# capturadas: uma requisição legítima chega em segundos, não em minutos.
MAX_TIMESTAMP_SKEW_SECONDS = 300


def build_signing_payload(timestamp: str, body: bytes) -> bytes:
    """Monta `timestamp + "." + corpo` como bytes, sem tocar no corpo."""
    return timestamp.encode("utf-8") + b"." + body


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Assina o corpo cru e devolve a assinatura em hexadecimal."""
    if not secret:
        raise ValueError("WEBHOOK_SECRET vazio: recuse-se a assinar sem segredo.")
    return hmac.new(
        secret.encode("utf-8"),
        build_signing_payload(timestamp, body),
        hashlib.sha256,
    ).hexdigest()


def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Confere a assinatura em tempo constante.

    `compare_digest` é obrigatório aqui: comparar com `==` vaza, pelo tempo de
    execução, quantos caracteres iniciais bateram, o que permite descobrir a
    assinatura byte a byte.
    """
    if not secret or not signature:
        return False
    expected = sign(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)


def current_timestamp() -> str:
    """Timestamp UTC em segundos (epoch), como string — formato do cabeçalho."""
    return str(int(datetime.now(timezone.utc).timestamp()))


def timestamp_is_fresh(
    timestamp: str, *, max_skew_seconds: int = MAX_TIMESTAMP_SKEW_SECONDS
) -> bool:
    """Rejeita timestamps antigos (replay) ou absurdamente no futuro."""
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    delta = abs(int(datetime.now(timezone.utc).timestamp()) - sent_at)
    return delta <= max_skew_seconds


def build_headers(secret: str, event_id: str, body: bytes) -> dict[str, str]:
    """Cabeçalhos completos de uma requisição de webhook assinada."""
    timestamp = current_timestamp()
    return {
        "Content-Type": "application/json",
        HEADER_EVENT_ID: event_id,
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: sign(secret, timestamp, body),
    }
