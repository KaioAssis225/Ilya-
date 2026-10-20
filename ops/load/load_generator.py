"""Gerador de carga controlada e validador de orçamento de conexões (P13).

Reutiliza `ops.benchmark_production_api` e `ops.benchmark_scenarios` para:
  - Política positiva/default-deny de staging/homologação (`check_load_allowed`),
    bloqueando `*.up.railway.app` e qualquer ambiente fora de staging/homologacao.
  - Autenticação técnica somente leitura em memória (`CanaryAuth`), lida apenas
    de variáveis de ambiente (nunca de argumentos de linha de comando).
  - Cálculo de orçamento de conexões PostgreSQL:
      conexoes_max_api = replicas * WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW)
    com reserva operacional explícita e verificação de `RATE_LIMIT_STORAGE_URI`
    compartilhado (Redis) quando `WEB_CONCURRENCY > 1` ou `replicas > 1`.
  - Rampa canônica 1 -> 5 -> 10 -> 20 usuários virtuais (40 condicional via
    `--include-stage-40`), com 60s de aquecimento e 300s por patamar.
  - Mistura representativa de leitura (35% produtos, 25% pedidos, 15% dashboard,
    15% diretórios condicionados a `--include-directories`, 10% CEP com
    `--postal-mode simulated` por padrão para não chamar ViaCEP/GeoAPI/Zippopotam).
  - Circuit breaker automático (aborto em erro >5% por 120s, p95 >5x baseline,
    indisponibilidade ou pressão de conexões/timeout de pool).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ops.benchmark_production_api import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    CanaryAuth,
    SampleResult,
    check_load_allowed,
    compute_percentile,
    compute_stats,
    make_request,
    stats_to_dict,
)
from ops.benchmark_scenarios import BenchmarkScenario  # noqa: E402


# ─── Constantes canônicas (P13) ───────────────────────────────────────────────

DEFAULT_STAGE_USERS: tuple[int, ...] = (1, 5, 10, 20)
CONDITIONAL_STAGE_40_USERS: int = 40
DEFAULT_WARMUP_SECONDS: float = 60.0
DEFAULT_STAGE_DURATION_SECONDS: float = 300.0
DEFAULT_PACING_SECONDS: float = 0.5

DEFAULT_DB_POOL_SIZE: int = 5
DEFAULT_DB_MAX_OVERFLOW: int = 5
DEFAULT_RESERVED_CONNECTIONS: int = 10
DEFAULT_POSTGRES_MAX_CONNECTIONS: int = 100
DEFAULT_SAFE_UTILIZATION_RATIO: float = 0.85


# ─── Mistura ponderada de cenários ────────────────────────────────────────────

@dataclass(frozen=True)
class WeightedScenario:
    scenario: BenchmarkScenario
    weight: int
    category: str
    simulated_only: bool = False


@dataclass(frozen=True)
class ScenarioMix:
    scenarios: tuple[WeightedScenario, ...]
    total_weight: int
    effective_shares: dict[str, float]
    limitations: tuple[str, ...] = ()


def build_scenario_mix(
    *,
    include_directories: bool = False,
    postal_mode: str = "simulated",
) -> ScenarioMix:
    """Constrói a mistura representativa de leitura para capacidade em homologação.

    Pesos nominais (soma = 100):
      - 35% products (20% include_total=false, 15% include_total=true)
      - 25% orders (GET /api/v1/orders?limit=20)
      - 15% dashboard (GET /api/v1/dashboard/overview?ranking_limit=5)
      - 15% directories (8% clients, 7% representatives) — somente quando
        `include_directories=True` após decisão de acesso sintético.
      - 10% postal (GET /api/v1/utils/cep/01001000) — simulado localmente por
        padrão (`postal_mode="simulated"`), sem chamar ViaCEP/GeoAPI/Zippopotam.
    """
    if postal_mode not in {"simulated", "live"}:
        raise ValueError("postal_mode deve ser 'simulated' ou 'live'.")

    active: list[WeightedScenario] = [
        WeightedScenario(
            BenchmarkScenario(
                name="products_list_no_total",
                route_template="GET /products",
                path="/api/v1/products?limit=20&include_total=false",
                expected_status=200,
                requires_auth=True,
            ),
            weight=20,
            category="products",
        ),
        WeightedScenario(
            BenchmarkScenario(
                name="products_list_with_total",
                route_template="GET /products",
                path="/api/v1/products?limit=20&include_total=true",
                expected_status=200,
                requires_auth=True,
            ),
            weight=15,
            category="products",
        ),
        WeightedScenario(
            BenchmarkScenario(
                name="orders_list",
                route_template="GET /orders",
                path="/api/v1/orders?limit=20",
                expected_status=200,
                requires_auth=True,
            ),
            weight=25,
            category="orders",
        ),
        WeightedScenario(
            BenchmarkScenario(
                name="dashboard_overview",
                route_template="GET /dashboard/overview",
                path="/api/v1/dashboard/overview?ranking_limit=5",
                expected_status=200,
                requires_auth=True,
            ),
            weight=15,
            category="dashboard",
        ),
    ]

    limitations: list[str] = []
    if include_directories:
        active.extend(
            [
                WeightedScenario(
                    BenchmarkScenario(
                        name="clients_list",
                        route_template="GET /clients",
                        path="/api/v1/clients?limit=20&include_total=false",
                        expected_status=200,
                        requires_auth=True,
                    ),
                    weight=8,
                    category="directories",
                ),
                WeightedScenario(
                    BenchmarkScenario(
                        name="representatives_list",
                        route_template="GET /representatives",
                        path="/api/v1/representatives?limit=20",
                        expected_status=200,
                        requires_auth=True,
                    ),
                    weight=7,
                    category="directories",
                ),
            ]
        )
    else:
        limitations.append(
            "Diretórios omitidos: o papel técnico P11 (benchmark_readonly) bloqueia "
            "/clients e /representatives; pesos ativos reponderados sobre 85 pontos."
        )

    is_simulated_postal = postal_mode == "simulated"
    active.append(
        WeightedScenario(
            BenchmarkScenario(
                name="postal_lookup",
                route_template="GET /utils/cep/{cep}",
                path="/api/v1/utils/cep/01001000",
                expected_status=200,
                requires_auth=False,
            ),
            weight=10,
            category="postal",
            simulated_only=is_simulated_postal,
        )
    )
    if is_simulated_postal:
        limitations.append(
            "CEP em modo simulado local: não realiza chamadas a ViaCEP/GeoAPI/Zippopotam."
        )

    total_weight = sum(item.weight for item in active)
    category_totals: dict[str, int] = {}
    for item in active:
        category_totals[item.category] = category_totals.get(item.category, 0) + item.weight
    effective_shares = {
        cat: round((w / total_weight) * 100.0, 2)
        for cat, w in category_totals.items()
    }

    return ScenarioMix(
        scenarios=tuple(active),
        total_weight=total_weight,
        effective_shares=effective_shares,
        limitations=tuple(limitations),
    )


def select_weighted_scenario(mix: ScenarioMix, rng: random.Random) -> WeightedScenario:
    """Seleciona deterministicamente um cenário respeitando os pesos ativos."""
    if mix.total_weight <= 0 or not mix.scenarios:
        raise ValueError("Mistura de cenários vazia.")
    target = rng.randint(1, mix.total_weight)
    acc = 0
    for item in mix.scenarios:
        acc += item.weight
        if target <= acc:
            return item
    return mix.scenarios[-1]


# ─── Orçamento de conexões PostgreSQL ─────────────────────────────────────────

@dataclass(frozen=True)
class ConnectionBudget:
    replicas: int
    web_concurrency: int
    db_pool_size: int
    db_max_overflow: int
    api_max_connections: int
    reserved_connections: int
    total_required_connections: int
    postgres_max_connections: int
    safe_utilization_ratio: float
    safe_connection_ceiling: int
    is_within_budget: bool
    validation_errors: tuple[str, ...] = ()


def calculate_connection_budget(
    *,
    replicas: int = 1,
    web_concurrency: int = 1,
    db_pool_size: int = DEFAULT_DB_POOL_SIZE,
    db_max_overflow: int = DEFAULT_DB_MAX_OVERFLOW,
    reserved_connections: int = DEFAULT_RESERVED_CONNECTIONS,
    postgres_max_connections: int = DEFAULT_POSTGRES_MAX_CONNECTIONS,
    safe_utilization_ratio: float = DEFAULT_SAFE_UTILIZATION_RATIO,
    rate_limit_storage_uri: str = "memory://",
) -> ConnectionBudget:
    """Calcula e valida o orçamento de conexões da API contra o limite do PostgreSQL.

    Fórmula canônica:
        conexões máximas da API = réplicas × WEB_CONCURRENCY × (DB_POOL_SIZE + DB_MAX_OVERFLOW)
    """
    errors: list[str] = []
    if replicas < 1:
        errors.append("replicas deve ser >= 1.")
    if web_concurrency < 1:
        errors.append("web_concurrency deve ser >= 1.")
    if db_pool_size < 1:
        errors.append("db_pool_size deve ser >= 1.")
    if db_max_overflow < 0:
        errors.append("db_max_overflow deve ser >= 0.")
    if reserved_connections < 1:
        errors.append("reserved_connections deve ser >= 1.")
    if postgres_max_connections < 10:
        errors.append("postgres_max_connections deve ser >= 10.")
    if not (0.1 <= safe_utilization_ratio <= 1.0):
        errors.append("safe_utilization_ratio deve estar entre 0.1 e 1.0.")

    if (web_concurrency > 1 or replicas > 1) and rate_limit_storage_uri.strip().startswith("memory://"):
        errors.append(
            "WEB_CONCURRENCY > 1 ou múltiplas réplicas exigem RATE_LIMIT_STORAGE_URI compartilhado (Redis)."
        )

    api_max = max(0, replicas) * max(0, web_concurrency) * (max(0, db_pool_size) + max(0, db_max_overflow))
    total_required = api_max + max(0, reserved_connections)
    safe_ceiling = int(max(0, postgres_max_connections) * safe_utilization_ratio)

    within_limits = (
        total_required <= postgres_max_connections
        and total_required <= safe_ceiling
    )
    if not within_limits and not errors:
        errors.append(
            f"Orçamento de conexões excede o teto seguro: total={total_required} "
            f"(API={api_max} + reserva={reserved_connections}) > teto={safe_ceiling} "
            f"(max_connections={postgres_max_connections})."
        )

    return ConnectionBudget(
        replicas=replicas,
        web_concurrency=web_concurrency,
        db_pool_size=db_pool_size,
        db_max_overflow=db_max_overflow,
        api_max_connections=api_max,
        reserved_connections=reserved_connections,
        total_required_connections=total_required,
        postgres_max_connections=postgres_max_connections,
        safe_utilization_ratio=safe_utilization_ratio,
        safe_connection_ceiling=safe_ceiling,
        is_within_budget=within_limits and not errors,
        validation_errors=tuple(errors),
    )


# ─── Critérios automáticos de aborto (Circuit Breaker) ────────────────────────

@dataclass(frozen=True)
class AbortReason:
    code: str
    message: str


@dataclass(frozen=True)
class StageAbortConfig:
    max_error_rate: float = 0.05
    error_window_seconds: float = 120.0
    max_p95_multiplier: float = 5.0
    max_consecutive_failures: int = 10


def evaluate_abort_condition(
    samples: Sequence[SampleResult],
    *,
    baseline_p95_ms: Optional[float],
    budget: ConnectionBudget,
    observed_db_connections: int = 0,
    observed_pool_timeouts: int = 0,
    config: StageAbortConfig = StageAbortConfig(),
    evaluation_duration_seconds: float = 0.0,
) -> Optional[AbortReason]:
    """Avalia se o patamar atual deve ser abortado imediatamente."""
    # 1. Pressão de conexões do banco ou timeout de pool (pode disparar mesmo antes de amostras)
    if observed_pool_timeouts > 0:
        return AbortReason(
            code="pool_timeout",
            message=f"Timeout de pool detectado (observed_pool_timeouts={observed_pool_timeouts}).",
        )
    if observed_db_connections >= budget.safe_connection_ceiling:
        return AbortReason(
            code="db_connection_ceiling",
            message=(
                f"Conexões observadas ({observed_db_connections}) atingiram o teto seguro "
                f"({budget.safe_connection_ceiling})."
            ),
        )

    non_warmup = [s for s in samples if not s.is_warmup]
    if not non_warmup:
        return None

    # 2. Indisponibilidade por falhas consecutivas de rede/timeout/5xx ou ausência total de 2xx
    consecutive_severe = 0
    for s in non_warmup:
        if s.is_network_error or s.is_functional_failure:
            consecutive_severe += 1
            if consecutive_severe >= config.max_consecutive_failures:
                return AbortReason(
                    code="unavailability",
                    message=f"{consecutive_severe} falhas severas consecutivas (5xx/rede/timeout).",
                )
        else:
            consecutive_severe = 0

    valid_latencies = sorted(
        s.latency_ms for s in non_warmup if s.is_valid_success and s.latency_ms is not None
    )
    error_count = sum(1 for s in non_warmup if not s.is_valid_success)
    if len(valid_latencies) == 0 and error_count >= config.max_consecutive_failures:
        return AbortReason(
            code="unavailability",
            message="Nenhuma resposta 2xx válida obtida no conjunto de amostras.",
        )

    # 3. Taxa de erro > 5% sustentada por 2 minutos (120s)
    if evaluation_duration_seconds >= config.error_window_seconds:
        error_rate = error_count / len(non_warmup)
        if error_rate > config.max_error_rate:
            return AbortReason(
                code="error_rate_exceeded",
                message=(
                    f"Taxa de erro {error_rate:.2%} excedeu o limite {config.max_error_rate:.2%} "
                    f"por {evaluation_duration_seconds:.0f}s."
                ),
            )

    # 4. p95 > 5x baseline (quando baseline_p95_ms foi informado e há amostra mínima)
    if baseline_p95_ms is not None and baseline_p95_ms > 0 and len(valid_latencies) >= 20:
        current_p95 = compute_percentile(valid_latencies, 95)
        limit_ms = baseline_p95_ms * config.max_p95_multiplier
        if current_p95 > limit_ms:
            return AbortReason(
                code="p95_degradation",
                message=f"p95 atual ({current_p95:.1f} ms) excedeu 5x o baseline ({limit_ms:.1f} ms).",
            )

    return None


# ─── Provedor postal simulado ─────────────────────────────────────────────────

def simulated_postal_request(
    _url: str,
    _headers: dict[str, str],
    _timeout: float,
) -> tuple[Optional[int], Optional[float], Optional[str]]:
    """Simula localmente a resposta de CEP sem realizar chamada HTTP externa."""
    return 200, 5.0, None


# ─── Execução de patamares de carga ───────────────────────────────────────────

@dataclass
class StageReport:
    stage_label: str
    virtual_users: int
    duration_seconds: float
    total_requests: int
    valid_requests: int
    error_rate: float
    requests_per_second: float
    scenario_stats: list[dict]
    aborted: bool
    abort_reason: Optional[dict[str, str]] = None


def run_stage_samples(
    *,
    stage_label: str,
    virtual_users: int,
    target_url: str,
    mix: ScenarioMix,
    warmup_seconds: float,
    stage_duration_seconds: float,
    pacing_seconds: float,
    seed: int,
    budget: ConnectionBudget,
    abort_config: StageAbortConfig = StageAbortConfig(),
    baseline_p95_ms: Optional[float] = None,
    auth_request_fn: Optional[Callable[[str, float], tuple[Optional[int], Optional[float], Optional[str]]]] = None,
    public_request_fn: Callable[[str, dict[str, str], float], tuple[Optional[int], Optional[float], Optional[str]]] = make_request,
    metrics_probe_fn: Optional[Callable[[], tuple[int, int]]] = None,
    max_iterations_per_user: Optional[int] = None,
) -> tuple[list[SampleResult], StageReport]:
    """Executa um patamar de carga com `virtual_users` concorrentes."""
    samples: list[SampleResult] = []
    lock = threading.Lock()
    stop_event = threading.Event()
    seq_counter = itertools.count(0)
    abort_holder: list[AbortReason] = []

    total_window = warmup_seconds + stage_duration_seconds
    t_start = time.monotonic()

    def worker(worker_idx: int) -> None:
        worker_rng = random.Random(seed + worker_idx * 997)
        iterations = 0
        while not stop_event.is_set():
            elapsed = time.monotonic() - t_start
            if elapsed >= total_window:
                break
            if max_iterations_per_user is not None and iterations >= max_iterations_per_user:
                break
            iterations += 1

            is_warmup = elapsed < warmup_seconds
            weighted = select_weighted_scenario(mix, worker_rng)
            sc = weighted.scenario
            full_url = target_url.rstrip("/") + sc.path

            if weighted.simulated_only:
                status, latency, err = simulated_postal_request(full_url, {}, DEFAULT_TIMEOUT_SECONDS)
            elif sc.requires_auth and auth_request_fn is not None:
                status, latency, err = auth_request_fn(full_url, DEFAULT_TIMEOUT_SECONDS)
            else:
                status, latency, err = public_request_fn(full_url, {}, DEFAULT_TIMEOUT_SECONDS)

            sample = SampleResult(
                route_template=sc.route_template,
                origin="railway" if not weighted.simulated_only else "simulated",
                latency_ms=latency,
                status_code=status,
                error_type=err,
                sequence=next(seq_counter),
                is_warmup=is_warmup,
                expected_status=sc.expected_status,
            )

            obs_conn, obs_timeouts = (0, 0)
            if metrics_probe_fn is not None:
                obs_conn, obs_timeouts = metrics_probe_fn()

            with lock:
                samples.append(sample)
                sustained_elapsed = max(0.0, (time.monotonic() - t_start) - warmup_seconds)
                reason = evaluate_abort_condition(
                    samples,
                    baseline_p95_ms=baseline_p95_ms,
                    budget=budget,
                    observed_db_connections=obs_conn,
                    observed_pool_timeouts=obs_timeouts,
                    config=abort_config,
                    evaluation_duration_seconds=sustained_elapsed,
                )
                if reason is not None and not abort_holder:
                    abort_holder.append(reason)
                    stop_event.set()
                    break

            if pacing_seconds > 0 and not stop_event.is_set():
                time.sleep(pacing_seconds)

    threads = [
        threading.Thread(target=worker, args=(idx,), daemon=True)
        for idx in range(virtual_users)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=max(5.0, total_window + 5.0))

    actual_duration = max(0.001, time.monotonic() - t_start - warmup_seconds)
    non_warmup = [s for s in samples if not s.is_warmup]
    valid_count = sum(1 for s in non_warmup if s.is_valid_success)
    error_count = len(non_warmup) - valid_count
    error_rate = (error_count / len(non_warmup)) if non_warmup else 0.0
    rps = len(non_warmup) / actual_duration if non_warmup else 0.0

    by_scenario: dict[tuple[str, str], list[SampleResult]] = {}
    for item in mix.scenarios:
        key = (item.scenario.name, item.scenario.route_template)
        by_scenario[key] = [
            s for s in samples if s.route_template == item.scenario.route_template
        ]

    scenario_stats = [
        stats_to_dict(compute_stats(name, tmpl, sc_samples))
        for (name, tmpl), sc_samples in by_scenario.items()
        if sc_samples
    ]

    abort_reason = abort_holder[0] if abort_holder else None
    report = StageReport(
        stage_label=stage_label,
        virtual_users=virtual_users,
        duration_seconds=round(actual_duration, 3),
        total_requests=len(non_warmup),
        valid_requests=valid_count,
        error_rate=round(error_rate, 4),
        requests_per_second=round(rps, 2),
        scenario_stats=scenario_stats,
        aborted=abort_reason is not None,
        abort_reason=(
            {"code": abort_reason.code, "message": abort_reason.message}
            if abort_reason is not None
            else None
        ),
    )
    return samples, report


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gerador de carga controlada e orçamento de conexões (P13)."
    )
    parser.add_argument("--target-url", default="", help="URL HTTPS de homologação (ou BENCHMARK_TARGET_URL).")
    parser.add_argument("--vercel-url", default="", help="URL HTTPS opcional da Vercel (ou BENCHMARK_VERCEL_URL).")
    parser.add_argument("--environment", default="", help="Ambiente (exige staging ou homologacao).")
    parser.add_argument("--include-stage-40", action="store_true", help="Habilita patamar condicional E (40 VUs).")
    parser.add_argument("--include-directories", action="store_true", help="Inclui /clients e /representatives.")
    parser.add_argument("--postal-mode", choices=("simulated", "live"), default="simulated")
    parser.add_argument("--warmup-seconds", type=float, default=DEFAULT_WARMUP_SECONDS)
    parser.add_argument("--stage-duration-seconds", type=float, default=DEFAULT_STAGE_DURATION_SECONDS)
    parser.add_argument("--pacing-seconds", type=float, default=DEFAULT_PACING_SECONDS)
    parser.add_argument("--replicas", type=int, default=1)
    parser.add_argument("--web-concurrency", type=int, default=1)
    parser.add_argument("--db-pool-size", type=int, default=DEFAULT_DB_POOL_SIZE)
    parser.add_argument("--db-max-overflow", type=int, default=DEFAULT_DB_MAX_OVERFLOW)
    parser.add_argument("--reserved-connections", type=int, default=DEFAULT_RESERVED_CONNECTIONS)
    parser.add_argument("--postgres-max-connections", type=int, default=DEFAULT_POSTGRES_MAX_CONNECTIONS)
    parser.add_argument("--safe-utilization-ratio", type=float, default=DEFAULT_SAFE_UTILIZATION_RATIO)
    parser.add_argument("--baseline-p95-ms", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", default="", help="Caminho para gravar relatório JSON sanitizado.")
    parser.add_argument("--dry-run", action="store_true", help="Imprime plano e orçamento sem abrir rede.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    target_url = (args.target_url or os.environ.get("BENCHMARK_TARGET_URL", "")).rstrip("/")
    vercel_url = (args.vercel_url or os.environ.get("BENCHMARK_VERCEL_URL", "")).rstrip("/")
    environment = args.environment or os.environ.get("BENCHMARK_ENVIRONMENT", "unknown")
    staging_allowlist = os.environ.get("BENCHMARK_STAGING_ALLOWLIST", "")
    rate_limit_uri = os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://")
    seed = args.seed if args.seed is not None else int(os.environ.get("BENCHMARK_SEED", "42"))

    canary_identifier = os.environ.get("ILYA_BENCHMARK_USERNAME", "")
    canary_password = os.environ.get("ILYA_BENCHMARK_PASSWORD", "")
    canary_market = os.environ.get("ILYA_BENCHMARK_MARKET", "")
    has_canary = bool(canary_identifier and canary_password and canary_market)

    budget = calculate_connection_budget(
        replicas=args.replicas,
        web_concurrency=args.web_concurrency,
        db_pool_size=args.db_pool_size,
        db_max_overflow=args.db_max_overflow,
        reserved_connections=args.reserved_connections,
        postgres_max_connections=args.postgres_max_connections,
        safe_utilization_ratio=args.safe_utilization_ratio,
        rate_limit_storage_uri=rate_limit_uri,
    )
    if not budget.is_within_budget:
        for err in budget.validation_errors:
            print(f"ERRO_ORCAMENTO: {err}", file=sys.stderr)
        return 2

    mix = build_scenario_mix(
        include_directories=args.include_directories,
        postal_mode=args.postal_mode,
    )

    stage_users = list(DEFAULT_STAGE_USERS)
    if args.include_stage_40:
        stage_users.append(CONDITIONAL_STAGE_40_USERS)

    plan = {
        "tool": "ilya_load_generator_p13",
        "environment": environment,
        "has_target_url": bool(target_url),
        "has_canary_credentials": has_canary,
        "stage_users": stage_users,
        "warmup_seconds": args.warmup_seconds,
        "stage_duration_seconds": args.stage_duration_seconds,
        "pacing_seconds": args.pacing_seconds,
        "postal_mode": args.postal_mode,
        "include_directories": args.include_directories,
        "effective_shares_pct": mix.effective_shares,
        "connection_budget": {
            "formula": "replicas * WEB_CONCURRENCY * (DB_POOL_SIZE + DB_MAX_OVERFLOW)",
            "replicas": budget.replicas,
            "web_concurrency": budget.web_concurrency,
            "db_pool_size": budget.db_pool_size,
            "db_max_overflow": budget.db_max_overflow,
            "api_max_connections": budget.api_max_connections,
            "reserved_connections": budget.reserved_connections,
            "total_required_connections": budget.total_required_connections,
            "postgres_max_connections": budget.postgres_max_connections,
            "safe_connection_ceiling": budget.safe_connection_ceiling,
            "is_within_budget": budget.is_within_budget,
        },
        "abort_criteria": {
            "max_error_rate": 0.05,
            "error_window_seconds": 120.0,
            "max_p95_multiplier": 5.0,
            "baseline_p95_ms": args.baseline_p95_ms,
        },
        "limitations": list(mix.limitations),
    }

    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if not target_url:
        print("ERRO: BENCHMARK_TARGET_URL é obrigatório fora de --dry-run.", file=sys.stderr)
        return 2

    allow_err = check_load_allowed(target_url, vercel_url, environment, staging_allowlist)
    if allow_err is not None:
        print(f"ERRO: {allow_err}", file=sys.stderr)
        return 2

    if not has_canary:
        print(
            "ERRO: execução de carga comercial exige ILYA_BENCHMARK_USERNAME, "
            "ILYA_BENCHMARK_PASSWORD e ILYA_BENCHMARK_MARKET no ambiente.",
            file=sys.stderr,
        )
        return 2

    try:
        canary = CanaryAuth(target_url, canary_identifier, canary_password, canary_market)
        canary.login()
        canary.verify_scope()
    except (ValueError, RuntimeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    stage_labels = ("A", "B", "C", "D", "E")
    stage_reports: list[dict] = []
    exit_code = 0

    for idx, users in enumerate(stage_users):
        label = stage_labels[idx] if idx < len(stage_labels) else f"S{idx + 1}"
        _, stage_rep = run_stage_samples(
            stage_label=label,
            virtual_users=users,
            target_url=target_url,
            mix=mix,
            warmup_seconds=args.warmup_seconds,
            stage_duration_seconds=args.stage_duration_seconds,
            pacing_seconds=args.pacing_seconds,
            seed=seed + idx * 100,
            budget=budget,
            baseline_p95_ms=args.baseline_p95_ms,
            auth_request_fn=canary.get,
        )
        stage_reports.append(
            {
                "stage": stage_rep.stage_label,
                "virtual_users": stage_rep.virtual_users,
                "duration_seconds": stage_rep.duration_seconds,
                "total_requests": stage_rep.total_requests,
                "valid_requests": stage_rep.valid_requests,
                "error_rate": stage_rep.error_rate,
                "requests_per_second": stage_rep.requests_per_second,
                "aborted": stage_rep.aborted,
                "abort_reason": stage_rep.abort_reason,
                "scenarios": stage_rep.scenario_stats,
            }
        )
        if stage_rep.aborted:
            exit_code = 1
            break

    full_output = {
        "plan": plan,
        "stages": stage_reports,
    }
    serialized = json.dumps(full_output, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
