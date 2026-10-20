"""Probe autenticado de pressão do pool via `/internal/metrics` de P10 (P13/R02).

Limitação estrutural: o registry de P10 é **por processo** (cada worker do
Gunicorn/Uvicorn mantém seu próprio acumulador) e o endpoint não identifica o
worker que respondeu. Um scrape pelo balanceador cai num processo arbitrário,
portanto só representa a API inteira quando existe exatamente **um** processo
(1 réplica × WEB_CONCURRENCY=1). Qualquer outra topologia é recusada até haver
coletor agregado ou sinal do PostgreSQL (`pg_stat_activity`).

Fail-closed: scrape com erro, status diferente de 200, série obrigatória
ausente, rótulo de workers divergente, contador reiniciado ou troca de processo
levantam `MetricsProbeError`; nenhum desses casos vira zero.
"""
from __future__ import annotations

import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_METRICS_PATH: str = "/internal/metrics"
DEFAULT_PROBE_INTERVAL_SECONDS: float = 5.0
DEFAULT_PROBE_TIMEOUT_SECONDS: float = 5.0
MAX_METRICS_BYTES: int = 1024 * 1024
SUPPORTED_TOPOLOGY: str = "replicas=1 x WEB_CONCURRENCY=1"

_SAMPLE_LINE = re.compile(r"^([A-Za-z_:][A-Za-z0-9_:]*)(\{[^}]*\})?\s+(\S+)$")
_LABEL_PAIR = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"')


class MetricsProbeError(RuntimeError):
    """Falha do probe; a mensagem nunca contém credencial nem corpo da resposta."""


@dataclass(frozen=True)
class PoolSnapshot:
    in_use: int
    pool_timeouts_total: int
    workers_label: str
    process_start_time: float


def check_metrics_coverage(*, replicas: int, web_concurrency: int) -> Optional[str]:
    """Retorna erro quando um scrape não cobre todos os processos da API."""
    if replicas == 1 and web_concurrency == 1:
        return None
    return (
        f"Métricas de pool de P10 são por processo e não cobrem replicas={replicas} x "
        f"WEB_CONCURRENCY={web_concurrency}; carga só é autorizada em {SUPPORTED_TOPOLOGY} "
        "até existir coletor agregado ou sinal do PostgreSQL."
    )


def build_metrics_url(target_url: str, metrics_path: str) -> str:
    """Monta a URL do scrape no mesmo host já validado pela allowlist."""
    if (
        not metrics_path.startswith("/")
        or metrics_path.startswith("//")
        or any(ch in metrics_path for ch in "?#\\@")
        or "://" in metrics_path
    ):
        raise ValueError("metrics-path deve ser caminho absoluto simples, sem query, fragmento ou host.")
    url = target_url.rstrip("/") + metrics_path
    if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(target_url).netloc:
        raise ValueError("metrics-path não pode trocar o host do alvo.")
    return url


def _parse_value(raw: str, series: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise MetricsProbeError(f"Valor não numérico em {series}.") from None
    if not math.isfinite(value) or value < 0:
        raise MetricsProbeError(f"Valor inválido em {series}.")
    return value


def _as_count(value: float, series: str) -> int:
    if value != int(value):
        raise MetricsProbeError(f"Valor não inteiro em {series}.")
    return int(value)


def parse_pool_metrics(text: str) -> PoolSnapshot:
    """Extrai as séries de pool do texto Prometheus de P10, de forma estrita."""
    in_use: list[float] = []
    timeouts: list[float] = []
    workers: list[str] = []
    start_times: list[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_LINE.match(line)
        if match is None:
            continue
        name, raw_labels, raw_value = match.groups()
        labels = dict(_LABEL_PAIR.findall(raw_labels or ""))
        if name == "ilya_db_pool_connections" and labels.get("state") == "in_use":
            in_use.append(_parse_value(raw_value, name))
        elif name == "ilya_db_pool_timeouts_total" and labels.get("pool") == "primary":
            timeouts.append(_parse_value(raw_value, name))
        elif name == "ilya_app_info":
            workers.append(labels.get("workers", ""))
        elif name == "ilya_process_start_time_seconds":
            start_times.append(_parse_value(raw_value, name))

    if len(in_use) != 1:
        raise MetricsProbeError(
            "Série ilya_db_pool_connections{state=\"in_use\"} ausente ou duplicada; "
            "observabilidade de pool não está instalada no processo."
        )
    if len(timeouts) > 1:
        raise MetricsProbeError("Série ilya_db_pool_timeouts_total duplicada.")
    if len(workers) != 1 or not workers[0]:
        raise MetricsProbeError("Série ilya_app_info ausente, duplicada ou sem rótulo workers.")
    if len(start_times) != 1:
        raise MetricsProbeError("Série ilya_process_start_time_seconds ausente ou duplicada.")

    # O registry de P10 cria contadores sob demanda: com o gauge de pool presente
    # (hooks instalados), a ausência do contador significa nenhum timeout neste
    # processo desde o início, e não falta de dado.
    timeout_total = _as_count(timeouts[0], "ilya_db_pool_timeouts_total") if timeouts else 0
    return PoolSnapshot(
        in_use=_as_count(in_use[0], "ilya_db_pool_connections"),
        pool_timeouts_total=timeout_total,
        workers_label=workers[0],
        process_start_time=start_times[0],
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def fetch_metrics_text(url: str, credential: str, timeout_seconds: float) -> str:
    """Scrape autenticado sem seguir redirect (o bearer nunca sai do host)."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {credential}"})
    try:
        with _OPENER.open(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise MetricsProbeError(f"Scrape de métricas respondeu {response.status}.")
            body = response.read(MAX_METRICS_BYTES + 1)
    except urllib.error.HTTPError as exc:
        hint = " (observabilidade desligada ou credencial recusada)" if exc.code == 404 else ""
        raise MetricsProbeError(f"Scrape de métricas respondeu {exc.code}{hint}.") from None
    except TimeoutError:
        raise MetricsProbeError("Scrape de métricas excedeu o tempo limite.") from None
    except (urllib.error.URLError, OSError):
        raise MetricsProbeError("Scrape de métricas indisponível (falha de rede).") from None
    if len(body) > MAX_METRICS_BYTES:
        raise MetricsProbeError("Resposta de métricas excede o limite de tamanho.")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        raise MetricsProbeError("Resposta de métricas não é UTF-8.") from None


class PoolPressureProbe:
    """Fornece `(conexões em uso, timeouts de pool desde prime())` para o aborto.

    O scrape é limitado a um por `min_interval_seconds` (relógio monotônico);
    entre scrapes devolve o último valor válido. Falhas nunca são cacheadas.
    """

    def __init__(
        self,
        fetch: Callable[[], str],
        *,
        expected_workers: int,
        min_interval_seconds: float = DEFAULT_PROBE_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds deve ser >= 0.")
        self._fetch = fetch
        self._expected_workers = str(expected_workers)
        self._interval = min_interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._baseline: Optional[PoolSnapshot] = None
        self._cached: Optional[tuple[int, int]] = None
        self._last_at: Optional[float] = None
        self.scrape_count = 0

    def _read(self) -> PoolSnapshot:
        self.scrape_count += 1
        try:
            text = self._fetch()
        except MetricsProbeError:
            raise
        except Exception as exc:  # transporte injetado: não propagar detalhe
            raise MetricsProbeError(f"Scrape de métricas falhou ({type(exc).__name__}).") from None
        if not isinstance(text, str):
            raise MetricsProbeError("Scrape de métricas não retornou texto.")
        snapshot = parse_pool_metrics(text)
        if snapshot.workers_label != self._expected_workers:
            raise MetricsProbeError(
                f"Processo reporta workers={snapshot.workers_label:.16}, esperado "
                f"{self._expected_workers}; cobertura de métricas incompleta."
            )
        return snapshot

    def prime(self) -> PoolSnapshot:
        """Primeiro scrape antes da carga: valida a fonte e fixa a linha de base."""
        with self._lock:
            snapshot = self._read()
            self._baseline = snapshot
            self._cached = (snapshot.in_use, 0)
            self._last_at = self._clock()
            return snapshot

    def __call__(self) -> tuple[int, int]:
        with self._lock:
            baseline = self._baseline
            if baseline is None:
                raise MetricsProbeError("Probe de pool não inicializado (prime ausente).")
            now = self._clock()
            if self._cached is not None and self._last_at is not None and now - self._last_at < self._interval:
                return self._cached
            snapshot = self._read()
            if snapshot.process_start_time != baseline.process_start_time:
                raise MetricsProbeError("Processo da API reiniciou ou mudou durante a carga.")
            if snapshot.pool_timeouts_total < baseline.pool_timeouts_total:
                raise MetricsProbeError("Contador de timeouts de pool regrediu (processo trocado).")
            self._cached = (snapshot.in_use, snapshot.pool_timeouts_total - baseline.pool_timeouts_total)
            self._last_at = now
            return self._cached
