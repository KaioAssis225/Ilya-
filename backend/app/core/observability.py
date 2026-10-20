"""Métricas locais de baixa cardinalidade, sem payload, URL ou identidade.

O módulo não depende de um coletor específico. Expõe texto Prometheus quando a
feature flag está ativa; cada worker mantém seu próprio acumulador em memória.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict
from contextvars import ContextVar
from typing import Any

import httpx
from sqlalchemy import event

from app.core.config import settings

ENABLED = settings.OBSERVABILITY_ENABLED
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_SAFE_ROUTE = re.compile(r"^/[A-Za-z0-9_./{}:-]{0,180}$")
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
_MARKETS = frozenset({"BR", "EU"})
_DEPENDENCIES = frozenset({"viacep", "geoapi", "zippopotam", "moloni", "microsoft_graph", "webhook", "unknown"})
_PROCESS_STARTED = time.time()
_db_acquire_started: ContextVar[float | None] = ContextVar("ilya_db_acquire_started", default=None)
_request_totals: ContextVar[dict[str, float] | None] = ContextVar("ilya_request_totals", default=None)


def _labels(**values: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(values.items()))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple], tuple[int, float, list[int]]] = {}

    def counter(self, name: str, amount: float = 1, **labels: str) -> None:
        if not ENABLED:
            return
        with self._lock:
            self._counters[(name, _labels(**labels))] += amount

    def gauge_add(self, name: str, amount: float, **labels: str) -> None:
        if not ENABLED:
            return
        with self._lock:
            key = (name, _labels(**labels))
            self._gauges[key] = max(0.0, self._gauges[key] + amount)

    def observe(self, name: str, value: float, **labels: str) -> None:
        if not ENABLED:
            return
        with self._lock:
            key = (name, _labels(**labels))
            count, total, buckets = self._histograms.get(key, (0, 0.0, [0] * len(_BUCKETS)))
            for index, upper in enumerate(_BUCKETS):
                if value <= upper:
                    buckets[index] += 1
            self._histograms[key] = (count + 1, total + value, buckets)

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {key: (value[0], value[1], list(value[2])) for key, value in self._histograms.items()}

        def suffix(labels: tuple[tuple[str, str], ...]) -> str:
            return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in labels) + "}" if labels else ""

        for name in sorted({name for name, _labels_value in counters}):
            lines.append(f"# TYPE {name} counter")
        for name in sorted({name for name, _labels_value in gauges}):
            lines.append(f"# TYPE {name} gauge")
        for name in sorted({name for name, _labels_value in histograms}):
            lines.append(f"# TYPE {name} histogram")
        for (name, labels), value in sorted(counters.items()):
            lines.append(f"{name}{suffix(labels)} {value:g}")
        for (name, labels), value in sorted(gauges.items()):
            lines.append(f"{name}{suffix(labels)} {value:g}")
        for (name, labels), (count, total, buckets) in sorted(histograms.items()):
            base = dict(labels)
            for upper, bucket_count in zip(_BUCKETS, buckets):
                lines.append(f'{name}_bucket{suffix(_labels(**base, le=str(upper)))} {bucket_count}')
            lines.append(f'{name}_bucket{suffix(_labels(**base, le="+Inf"))} {count}')
            lines.append(f"{name}_sum{suffix(labels)} {total:g}")
            lines.append(f"{name}_count{suffix(labels)} {count}")
        lines.extend(_process_lines())
        lines.append("# EOF")
        return "\n".join(lines) + "\n"


registry = Registry()
_pool: Any = None


def begin_request() -> object:
    return _request_totals.set({"sql_seconds": 0.0, "sql_count": 0.0, "acquire_seconds": 0.0, "acquire_count": 0.0, "external_seconds": 0.0, "external_count": 0.0})


def request_totals() -> dict[str, float]:
    return dict(_request_totals.get() or {})


def end_request(token: object) -> None:
    _request_totals.reset(token)  # type: ignore[arg-type]


def _add_request_total(kind: str, duration: float) -> None:
    totals = _request_totals.get()
    if totals is not None:
        totals[f"{kind}_seconds"] += max(0.0, duration)
        totals[f"{kind}_count"] += 1


def safe_method(value: str) -> str:
    value = value.upper()
    return value if value in _METHODS else "OTHER"


def safe_market(value: object) -> str:
    return value if isinstance(value, str) and value in _MARKETS else "none"


def safe_route(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and _SAFE_ROUTE.fullmatch(template) else "unmapped"


def http_started(method: str) -> None:
    registry.gauge_add("ilya_http_requests_in_flight", 1, method=safe_method(method))


def http_finished(*, method: str, route: str, status: int, market: object, duration: float, response_bytes: int | None, cancelled: bool = False) -> None:
    method = safe_method(method)
    route = route if _SAFE_ROUTE.fullmatch(route) else "unmapped"
    market = safe_market(market)
    status_text = str(status if 100 <= status <= 599 else 500)
    registry.gauge_add("ilya_http_requests_in_flight", -1, method=method)
    registry.counter("ilya_http_requests_total", method=method, route=route, status=status_text, market=market)
    registry.observe("ilya_http_request_duration_seconds", duration, method=method, route=route, market=market)
    if response_bytes is not None and response_bytes >= 0:
        registry.counter("ilya_http_response_bytes_total", float(response_bytes), method=method, route=route, market=market)
        registry.counter("ilya_http_responses_with_size_total", method=method, route=route, market=market)
    if cancelled:
        registry.counter("ilya_http_cancellations_total", method=method, route=route, market=market)


def begin_db_acquire() -> object:
    return _db_acquire_started.set(time.perf_counter())


def end_db_acquire(token: object, *, timed_out: bool = False) -> None:
    started = _db_acquire_started.get()
    if started is not None:
        duration = time.perf_counter() - started
        registry.observe("ilya_db_connection_acquire_duration_seconds", duration, pool="primary")
        _add_request_total("acquire", duration)
    if timed_out:
        registry.counter("ilya_db_pool_timeouts_total", pool="primary")
    _db_acquire_started.reset(token)  # type: ignore[arg-type]


def _query_class(context: object) -> str:
    compiled = getattr(context, "compiled", None)
    statement = getattr(compiled, "statement", None)
    visit_name = str(getattr(statement, "__visit_name__", "")).upper()
    return visit_name if visit_name in {"SELECT", "INSERT", "UPDATE", "DELETE"} else "OTHER"


def install_sqlalchemy(engine: Any) -> None:
    global _pool
    if not ENABLED or getattr(engine.sync_engine, "_ilya_observability", False):
        return
    sync_engine = engine.sync_engine
    sync_engine._ilya_observability = True
    _pool = sync_engine.pool

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, _cursor, _statement, _parameters, context, _executemany):
        conn.info.setdefault("ilya_query_started", []).append((time.perf_counter(), _query_class(context)))

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, _cursor, _statement, _parameters, _context, _executemany):
        started, query_class = conn.info["ilya_query_started"].pop()
        duration = time.perf_counter() - started
        registry.observe("ilya_db_query_duration_seconds", duration, operation=query_class)
        _add_request_total("sql", duration)

    @event.listens_for(sync_engine, "handle_error")
    def handle_error(context):
        registry.counter("ilya_db_errors_total", operation="OTHER")
        stack = context.connection.info.get("ilya_query_started", []) if context.connection else []
        if stack:
            started, query_class = stack.pop()
            duration = time.perf_counter() - started
            registry.observe("ilya_db_query_duration_seconds", duration, operation=query_class)
            _add_request_total("sql", duration)


def dependency_name(request: httpx.Request) -> str:
    explicit = request.extensions.get("ilya_dependency")
    if explicit in _DEPENDENCIES:
        return explicit
    host = (request.url.host or "").lower()
    if host == "viacep.com.br": return "viacep"
    if host == "json.geoapi.pt": return "geoapi"
    if host == "api.zippopotam.us": return "zippopotam"
    if host.endswith("moloni.pt"): return "moloni"
    if host in {"graph.microsoft.com", "login.microsoftonline.com"}: return "microsoft_graph"
    return "unknown"


async def external_request_started(request: httpx.Request) -> None:
    if ENABLED:
        request.extensions["ilya_observability_started"] = time.perf_counter()


async def external_response(response: httpx.Response) -> None:
    if not ENABLED:
        return
    started = response.request.extensions.pop("ilya_observability_started", time.perf_counter())
    dependency = dependency_name(response.request)
    registry.counter("ilya_external_http_requests_total", dependency=dependency, outcome="http", status=str(response.status_code))
    duration = time.perf_counter() - started
    registry.observe("ilya_external_http_duration_seconds", duration, dependency=dependency)
    _add_request_total("external", duration)


def external_exception(exc: BaseException) -> None:
    if not ENABLED:
        return
    # O hook de resposta já contou o status HTTP; raise_for_status não deve
    # transformar a mesma chamada em uma segunda amostra.
    if isinstance(exc, httpx.HTTPStatusError):
        return
    request = getattr(exc, "request", None)
    dependency = dependency_name(request) if isinstance(request, httpx.Request) else "unknown"
    started = request.extensions.pop("ilya_observability_started", time.perf_counter()) if isinstance(request, httpx.Request) else time.perf_counter()
    outcome = "timeout" if isinstance(exc, httpx.TimeoutException) else "connect_error" if isinstance(exc, httpx.ConnectError) else "error"
    registry.counter("ilya_external_http_requests_total", dependency=dependency, outcome=outcome, status="none")
    duration = time.perf_counter() - started
    registry.observe("ilya_external_http_duration_seconds", duration, dependency=dependency)
    _add_request_total("external", duration)


def external_observe(dependency: str, *, status: int | None, outcome: str, duration: float) -> None:
    dependency = dependency if dependency in _DEPENDENCIES else "unknown"
    safe_outcome = outcome if outcome in {"http", "timeout", "connect_error", "error"} else "error"
    registry.counter(
        "ilya_external_http_requests_total",
        dependency=dependency,
        outcome=safe_outcome,
        status=str(status) if status is not None and 100 <= status <= 599 else "none",
    )
    registry.observe("ilya_external_http_duration_seconds", max(0.0, duration), dependency=dependency)
    _add_request_total("external", duration)


def external_invalid(dependency: str) -> None:
    registry.counter("ilya_external_invalid_responses_total", dependency=dependency if dependency in _DEPENDENCIES else "unknown")


def external_fallback(dependency: str) -> None:
    registry.counter("ilya_external_fallbacks_total", dependency=dependency if dependency in _DEPENDENCIES else "unknown")


def httpx_event_hooks() -> dict[str, list]:
    return {"request": [external_request_started], "response": [external_response]} if ENABLED else {}


def _rss_bytes() -> int:
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            return int(statm.read().split()[1]) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, IndexError):
        return 0


def _process_lines() -> list[str]:
    workers = os.environ.get("WEB_CONCURRENCY", "1")
    workers = workers if workers.isdigit() and 1 <= int(workers) <= 128 else "unknown"
    lines = [
        "# TYPE ilya_process_cpu_seconds_total counter",
        f"ilya_process_cpu_seconds_total {time.process_time():g}",
        "# TYPE ilya_process_resident_memory_bytes gauge",
        f"ilya_process_resident_memory_bytes {_rss_bytes()}",
        "# TYPE ilya_process_start_time_seconds gauge",
        f"ilya_process_start_time_seconds {_PROCESS_STARTED:.17g}",
        "# TYPE ilya_app_info gauge",
        f'ilya_app_info{{version="{_escape(settings.APP_VERSION)}",workers="{workers}"}} 1',
    ]
    if _pool is not None:
        size = max(0, _pool.size())
        checked_out = max(0, _pool.checkedout())
        overflow = max(0, _pool.overflow())
        available = max(0, size + overflow - checked_out)
        lines.extend((
            "# TYPE ilya_db_pool_connections gauge",
            f'ilya_db_pool_connections{{state="in_use"}} {checked_out}',
            f'ilya_db_pool_connections{{state="available"}} {available}',
            f'ilya_db_pool_connections{{state="overflow"}} {overflow}',
        ))
    return lines
