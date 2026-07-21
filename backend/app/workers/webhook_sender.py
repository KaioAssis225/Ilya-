"""Worker de entrega dos eventos da Outbox para o Ilya Estoque.

Processo SEPARADO da API, de propósito. Ele nunca deve ser passo de boot do
servidor web: se a entrega de webhook falhar, quem não pode cair é a API.

    python -m app.workers.webhook_sender

Garantias:

* **at-least-once** — um evento pode chegar duas vezes ao receptor, nunca se
  perde em silêncio. Descartar duplicata é responsabilidade do receptor, pelo
  `event_id`.
* **seguro com várias réplicas** — o lote é reservado com
  ``FOR UPDATE SKIP LOCKED``. Sem isso, dois workers pegariam as mesmas linhas
  e enviariam o mesmo evento em paralelo.
* **inerte por padrão** — sem ``WEBHOOK_ENABLED=true`` o worker se recusa a
  rodar.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.core import webhook_signature as ws
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.integration_outbox import IntegrationOutbox
from app.services.integration_events import serialize_envelope

logger = logging.getLogger("ilya.webhook_sender")

# Escada de retentativas (seção 11 do contrato). O índice é o número de
# tentativas JÁ realizadas: após a 1ª falha espera 1min, após a 2ª 5min, etc.
RETRY_DELAYS_SECONDS: tuple[int, ...] = (60, 300, 900, 3600, 21600, 86400)

BATCH_SIZE = 50
IDLE_SLEEP_SECONDS = 5.0

# Resultado da classificação de uma resposta HTTP.
DELIVERED = "delivered"
RETRY = "retry"
DEAD_LETTER = "dead_letter"


def classify_response(status_code: int) -> str:
    """Traduz o código HTTP na decisão do worker (seção 11 do contrato)."""
    if 200 <= status_code < 300:
        return DELIVERED
    if status_code == 429 or status_code >= 500:
        # Sobrecarga ou falha temporária do receptor: insistir faz sentido.
        return RETRY
    # 400 (contrato inválido), 401/403 (assinatura/permissão) e 409 (conflito)
    # não melhoram com repetição — repetir só geraria ruído. Vão para análise.
    return DEAD_LETTER


def next_delay_seconds(attempts: int) -> int | None:
    """Espera até a próxima tentativa, ou None se a escada acabou."""
    if attempts <= 0:
        return RETRY_DELAYS_SECONDS[0]
    if attempts > len(RETRY_DELAYS_SECONDS):
        return None
    return RETRY_DELAYS_SECONDS[attempts - 1]


def _truncate_error(message: str, limit: int = 500) -> str:
    """Erro resumido: nunca o corpo inteiro, nunca o segredo."""
    flat = " ".join(str(message).split())
    return flat[:limit]


def _retry_after_seconds(response: httpx.Response) -> int | None:
    """Respeita o cabeçalho Retry-After num 429, quando ele vem em segundos."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None


async def _claim_batch(session, limit: int = BATCH_SIZE) -> list[IntegrationOutbox]:
    """Reserva os eventos prontos para envio, travando as linhas do lote.

    ``skip_locked`` faz cada réplica pegar um conjunto distinto em vez de
    esperar pela outra.
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(IntegrationOutbox)
        .where(
            IntegrationOutbox.status == "pending",
            IntegrationOutbox.next_attempt_at <= now,
        )
        .order_by(IntegrationOutbox.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def deliver_one(client: httpx.AsyncClient, row: IntegrationOutbox) -> None:
    """Tenta entregar um evento e atualiza seu estado na outbox.

    Não faz commit: quem controla a transação é o chamador (`process_batch`).
    """
    body = serialize_envelope(row.payload)
    headers = ws.build_headers(settings.WEBHOOK_SECRET, str(row.event_id), body)
    row.attempts = (row.attempts or 0) + 1

    try:
        response = await client.post(
            settings.WEBHOOK_URL,
            content=body,
            headers=headers,
            timeout=settings.WEBHOOK_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        # Rede fora, DNS, timeout: sempre retentável.
        _schedule_retry(row, _truncate_error(f"{type(exc).__name__}: {exc}"))
        return

    outcome = classify_response(response.status_code)

    if outcome == DELIVERED:
        row.status = "delivered"
        row.delivered_at = datetime.now(timezone.utc)
        row.last_error = None
        return

    error = _truncate_error(f"HTTP {response.status_code}: {response.text}")

    if outcome == DEAD_LETTER:
        row.status = "dead_letter"
        row.last_error = error
        logger.error(
            "Evento %s (%s) em dead_letter: HTTP %s",
            row.event_id,
            row.event_type,
            response.status_code,
        )
        return

    _schedule_retry(row, error, override_delay=_retry_after_seconds(response))


def _schedule_retry(
    row: IntegrationOutbox, error: str, *, override_delay: int | None = None
) -> None:
    """Agenda a próxima tentativa ou encerra o evento em dead_letter."""
    delay = (
        override_delay if override_delay is not None else next_delay_seconds(row.attempts)
    )

    if delay is None or row.attempts >= settings.WEBHOOK_MAX_ATTEMPTS:
        row.status = "dead_letter"
        row.last_error = error
        logger.error(
            "Evento %s (%s) esgotou as tentativas: %s",
            row.event_id,
            row.event_type,
            error,
        )
        return

    row.status = "pending"
    row.last_error = error
    row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)


async def process_batch(client: httpx.AsyncClient) -> dict[str, int]:
    """Processa um lote e devolve a contagem por desfecho."""
    stats = {"claimed": 0, "delivered": 0, "pending": 0, "dead_letter": 0}

    async with AsyncSessionLocal() as session:
        async with session.begin():
            rows = await _claim_batch(session)
            stats["claimed"] = len(rows)
            for row in rows:
                await deliver_one(client, row)
                stats[row.status] = stats.get(row.status, 0) + 1

    return stats


async def run_forever() -> None:
    """Laço principal: drena a outbox e dorme quando não há nada a fazer."""
    async with httpx.AsyncClient(follow_redirects=False) as client:
        while True:
            try:
                stats = await process_batch(client)
            except Exception:  # pragma: no cover - resiliência do laço
                # Um erro aqui não pode matar o worker; ele precisa continuar
                # tentando nos ciclos seguintes.
                logger.exception("Falha ao processar lote da outbox")
                await asyncio.sleep(IDLE_SLEEP_SECONDS)
                continue

            if stats["claimed"] == 0:
                await asyncio.sleep(IDLE_SLEEP_SECONDS)
            else:
                logger.info("Lote processado: %s", stats)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if not settings.WEBHOOK_ENABLED:
        logger.info("WEBHOOK_ENABLED=false; worker nao inicia (feature inerte).")
        return
    if not settings.WEBHOOK_URL or not settings.WEBHOOK_SECRET:
        raise RuntimeError(
            "WEBHOOK_ENABLED=true exige WEBHOOK_URL e WEBHOOK_SECRET configurados."
        )

    logger.info("Worker de webhooks iniciado (destino: %s)", settings.WEBHOOK_URL)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
