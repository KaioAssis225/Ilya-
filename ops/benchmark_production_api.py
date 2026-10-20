"""Ferramenta de diagnóstico e benchmark reproduzível para a API do Ilya.

Modos de execução:
  smoke    — 3 amostras por origem; p95/p99 marcados como inconclusivos.
  baseline — 5 warmups por origem + 30 amostras válidas por origem; percentis conclusivos.
  load     — rampa de concorrência; restrito a ambiente staging/homologacao com allowlist.

Políticas de integridade:
  - valid_count e percentis só incluem respostas 2xx bem-sucedidas.
  - 401/403 ficam em auth_failure_count; nunca são operação válida.
  - 4xx não-auth ficam em client_error_count.
  - 5xx ficam em functional_failure_count e causam exit 1.
  - Erros de rede e timeout ficam em contadores separados, fora da distribuição.
  - Estatísticas produzidas separadamente por origem (Railway / Vercel).
  - Cada origem recebe warmup_count warmups e até sample_count amostras válidas.
  - Authorization e cabeçalhos sensíveis são redactados antes de qualquer saída.

Políticas de segurança do modo load (política positiva/default-deny):
  - Só roda quando BENCHMARK_ENVIRONMENT é "staging" ou "homologacao" E
    cada host está em BENCHMARK_STAGING_ALLOWLIST (lista separada por vírgula).
  - Domínios *.up.railway.app são sempre bloqueados.
  - Configuração inválida retorna exit 2.

Códigos de saída:
  0 — sucesso real.
  1 — falha de rede total, ausência de amostra válida (não por auth) ou falha 5xx.
  2 — configuração inválida ou modo não autorizado.

Credenciais via variável de ambiente (NUNCA como argumento de linha de comando):
  BENCHMARK_API_TOKEN        — Bearer token para rotas autenticadas
  BENCHMARK_TARGET_URL       — URL base da API (Railway)
  BENCHMARK_VERCEL_URL       — URL base do Vercel para comparação
  BENCHMARK_ENVIRONMENT      — nome do ambiente (ex: homologacao, producao)
  BENCHMARK_SEED             — inteiro para reprodutibilidade (padrão: 42)
  BENCHMARK_STAGING_ALLOWLIST — hostnames de staging permitidos para modo load
                                (separados por vírgula; apenas hostnames simples,
                                 ex: "host.example.com" — nunca URLs completas)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    from ops.benchmark_scenarios import BenchmarkScenario, FIXTURE_SCENARIOS, select_scenarios
except ModuleNotFoundError:  # execução direta: python ops/benchmark_production_api.py
    from benchmark_scenarios import BenchmarkScenario, FIXTURE_SCENARIOS, select_scenarios


# ─── Constantes ───────────────────────────────────────────────────────────────

MIN_SAMPLES_FOR_PERCENTILES: int = 30
MIN_WARMUP_BASELINE: int = 5
SMOKE_SAMPLE_COUNT: int = 3
DEFAULT_TIMEOUT_SECONDS: float = 10.0
MAX_ATTEMPTS_MULTIPLIER: int = 3  # max_attempts = sample_count * n_origens * este valor

STAGING_ENVS: frozenset[str] = frozenset({"staging", "homologacao"})

_UP_RAILWAY_APP_PATTERN = re.compile(r"\.up\.railway\.app", re.IGNORECASE)

LOAD_MAX_WORKERS: int = 50
LOAD_MAX_STAGES: int = 10
LOAD_MAX_REQUESTS_PER_STAGE: int = 100
LOAD_DEFAULT_WORKERS: int = 4
LOAD_DEFAULT_STAGES: int = 3
LOAD_DEFAULT_REQUESTS_PER_STAGE: int = 10

_SECRET_HEADERS: frozenset[str] = frozenset({
    "authorization",
    "x-api-key",
    "cookie",
    "set-cookie",
    "x-auth-token",
})


# ─── Modelos de dados ──────────────────────────────────────────────────────────

@dataclass
class SampleResult:
    """Resultado de uma única requisição HTTP."""
    route_template: str
    origin: str
    latency_ms: Optional[float]
    status_code: Optional[int]
    error_type: Optional[str]  # None | "network" | "timeout"
    sequence: int
    is_warmup: bool = False
    expected_status: int | None = None

    @property
    def is_network_error(self) -> bool:
        return self.error_type in ("network", "timeout")

    @property
    def is_auth_failure(self) -> bool:
        return self.status_code in (401, 403)

    @property
    def is_valid_success(self) -> bool:
        """2xx — única categoria que conta como operação comercial válida."""
        if self.is_network_error or self.status_code is None:
            return False
        if self.expected_status is not None:
            return self.status_code == self.expected_status
        return 200 <= self.status_code < 300

    @property
    def is_client_error(self) -> bool:
        """4xx excluindo falhas de autenticação (401, 403)."""
        if self.is_network_error or self.status_code is None:
            return False
        return 400 <= self.status_code < 500 and self.status_code not in (401, 403)

    @property
    def is_functional_failure(self) -> bool:
        """5xx ou status ausente sem ser erro de rede. Causa exit 1."""
        if self.is_network_error:
            return False
        if self.status_code is None:
            return True
        return self.status_code >= 500


@dataclass
class ScenarioStats:
    """Estatísticas calculadas para um cenário (por origem)."""
    name: str
    route_template: str
    sample_count: int
    valid_count: int            # apenas 2xx
    network_error_count: int
    timeout_count: int
    auth_failure_count: int
    client_error_count: int     # 4xx excluindo 401/403
    functional_failure_count: int
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    p99_ms: Optional[float]
    max_ms: Optional[float]
    p95_conclusive: bool
    p99_conclusive: bool
    origins_tested: list[str] = field(default_factory=list)
    unexpected_status_count: int = 0


# ─── Estatística ───────────────────────────────────────────────────────────────

def compute_percentile(sorted_values: list[float], p: float) -> float:
    """Percentil via interpolação linear (método C2 — idêntico ao NumPy/NIST).

    sorted_values deve estar ordenado crescentemente; p em [0, 100].
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("Lista vazia para cálculo de percentil")
    if n == 1:
        return sorted_values[0]
    index = (p / 100.0) * (n - 1)
    lower = int(index)
    fraction = index - lower
    upper = lower + 1
    if upper >= n:
        return sorted_values[-1]
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def compute_stats(
    name: str,
    route_template: str,
    samples: list[SampleResult],
) -> ScenarioStats:
    """Calcula estatísticas para o conjunto de amostras.

    Apenas respostas 2xx entram em valid_count e nos percentis.
    Warmups, erros de rede, timeouts, 401/403 e 4xx/5xx não contam como válidos.
    """
    non_warmup = [s for s in samples if not s.is_warmup]

    valid_latencies = sorted(
        s.latency_ms
        for s in non_warmup
        if s.is_valid_success and s.latency_ms is not None
    )

    network_errors = sum(1 for s in non_warmup if s.error_type == "network")
    timeouts = sum(1 for s in non_warmup if s.error_type == "timeout")
    auth_failures = sum(1 for s in non_warmup if s.is_auth_failure)
    client_errors = sum(1 for s in non_warmup if s.is_client_error)
    functional_failures = sum(1 for s in non_warmup if s.is_functional_failure)
    unexpected_statuses = sum(
        1 for s in non_warmup
        if s.expected_status is not None and s.status_code is not None
        and s.status_code != s.expected_status
    )

    n_valid = len(valid_latencies)
    is_conclusive = n_valid >= MIN_SAMPLES_FOR_PERCENTILES

    p50 = compute_percentile(valid_latencies, 50) if valid_latencies else None
    p95 = compute_percentile(valid_latencies, 95) if valid_latencies else None
    p99 = compute_percentile(valid_latencies, 99) if valid_latencies else None
    max_ms = valid_latencies[-1] if valid_latencies else None

    origins_tested = sorted({s.origin for s in non_warmup})

    return ScenarioStats(
        name=name,
        route_template=route_template,
        sample_count=len(non_warmup),
        valid_count=n_valid,
        network_error_count=network_errors,
        timeout_count=timeouts,
        auth_failure_count=auth_failures,
        client_error_count=client_errors,
        functional_failure_count=functional_failures,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        max_ms=max_ms,
        p95_conclusive=is_conclusive,
        p99_conclusive=is_conclusive,
        origins_tested=origins_tested,
        unexpected_status_count=unexpected_statuses,
    )


# ─── Segurança ─────────────────────────────────────────────────────────────────

def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Substitui valores de cabeçalhos sensíveis por '***REDACTED***'."""
    return {
        k: ("***REDACTED***" if k.lower() in _SECRET_HEADERS else v)
        for k, v in headers.items()
    }


def check_load_allowed(
    target_url: str,
    vercel_url: str,
    environment: str,
    staging_allowlist_raw: str,
) -> Optional[str]:
    """Política positiva/default-deny para modo load.

    A allowlist (BENCHMARK_STAGING_ALLOWLIST) é a raiz de confiança operacional:
    apenas hostnames de homologação confirmados podem constar nela — nunca hosts
    de produção, URLs completas ou wildcards. Qualquer entrada inválida bloqueia
    imediatamente em vez de ser silenciada.

    Retorna None se permitido; mensagem de erro se bloqueado.

    Requisitos:
      - environment deve ser "staging" ou "homologacao".
      - Cada entrada da allowlist deve ser um hostname simples (sem "://").
        Exemplo válido: "host.example.com". Hostnames são normalizados para
        lowercase e sem ponto final antes da comparação.
      - target_url e vercel_url devem usar HTTPS sem userinfo, query ou fragment.
      - Nenhum host pode ser subdomínio de .up.railway.app.
      - O hostname normalizado de cada URL deve constar na allowlist.
    """
    if environment not in STAGING_ENVS:
        return (
            f"Ambiente '{environment}' não é staging/homologacao. "
            "Modo load exige BENCHMARK_ENVIRONMENT=staging ou homologacao."
        )

    if not staging_allowlist_raw.strip():
        return (
            "BENCHMARK_STAGING_ALLOWLIST não configurado. "
            "Modo load requer allowlist explícita de hostnames de staging."
        )

    # Parse e valida entradas da allowlist — devem ser hostnames, não URLs
    raw_entries = [e.strip() for e in staging_allowlist_raw.split(",") if e.strip()]
    if not raw_entries:
        return (
            "BENCHMARK_STAGING_ALLOWLIST está vazia após parsing. "
            "Informe pelo menos um hostname de staging."
        )

    allowlist: set[str] = set()
    for entry in raw_entries:
        if "://" in entry:
            return (
                f"Entrada de allowlist '{entry}' contém esquema de URL. "
                "BENCHMARK_STAGING_ALLOWLIST deve conter apenas hostnames simples "
                "(ex: host.example.com), não URLs completas."
            )
        normalized_entry = entry.lower().rstrip(".")
        if not normalized_entry:
            return "Entrada de allowlist inválida (vazia após normalização)."
        allowlist.add(normalized_entry)

    # Valida cada URL e compara hostname contra allowlist
    for url, label in [(target_url, "target-url"), (vercel_url, "vercel-url")]:
        if not url:
            continue

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return f"{label} não é uma URL válida."

        if parsed.scheme != "https":
            return (
                f"{label} deve usar esquema HTTPS "
                f"(recebido: '{parsed.scheme}'). "
                "Modo load não permite HTTP nem outros esquemas."
            )

        if parsed.username or parsed.password:
            return (
                f"{label} não pode conter userinfo (usuário:senha) na URL. "
                "Use BENCHMARK_API_TOKEN para credenciais."
            )

        if parsed.query:
            return f"{label} não pode conter query string na URL."

        if parsed.fragment:
            return f"{label} não pode conter fragmento (#) na URL."

        host = parsed.hostname  # urlparse já normaliza para lowercase e remove porta
        if not host:
            return f"{label} não tem hostname válido."

        host_norm = host.rstrip(".")

        if _UP_RAILWAY_APP_PATTERN.search(host_norm):
            return (
                f"{label} usa domínio .up.railway.app, bloqueado para modo load. "
                "Use o domínio de staging configurado explicitamente."
            )

        if host_norm not in allowlist:
            return (
                f"{label} '{host_norm}' não está em BENCHMARK_STAGING_ALLOWLIST. "
                "Adicione o hostname de staging explicitamente na allowlist "
                "(apenas hosts de homologação confirmados)."
            )

    return None


# ─── Reprodutibilidade ─────────────────────────────────────────────────────────

def alternate_origins(origins: list[str], count: int, seed: int) -> list[str]:
    """Retorna `count` origens em rotação determinística iniciada pelo seed.

    offset = seed % len(origins); rotação circular. Mesma seed = mesma sequência.
    """
    if not origins:
        raise ValueError("Lista de origens vazia")
    offset = seed % len(origins)
    return [origins[(offset + i) % len(origins)] for i in range(count)]


# ─── Rede ──────────────────────────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def _open_no_redirect(request, timeout: float):
    """Nunca encaminha senha ou bearer token a outro host por redirect."""
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)

def make_request(
    url: str,
    headers: dict[str, str],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[Optional[int], Optional[float], Optional[str]]:
    """Realiza uma requisição HTTP usando apenas a biblioteca padrão.

    Retorna (status_code, latency_ms, error_type).
    """
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers=headers)
        with _open_no_redirect(req, timeout_seconds) as resp:
            elapsed = (time.perf_counter() - start) * 1000.0
            return resp.status, elapsed, None
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return exc.code, elapsed, None
    except TimeoutError:
        return None, None, "timeout"
    except (urllib.error.URLError, OSError):
        return None, None, "network"


class CanaryAuth:
    """Access token técnico mantido só em memória; renova por novo login.

    O cookie de refresh não é armazenado: o fluxo de benchmark não depende
    de uma origem CORS e nunca envia cookie ao servidor de aplicação.
    """

    def __init__(self, base_url: str, identifier: str, password: str, market: str):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("Canário exige URL HTTPS sem credenciais embutidas.")
        if market not in {"BR", "EU"} or not identifier or not password:
            raise ValueError("Identidade técnica e mercado BR/EU são obrigatórios.")
        self.base_url = base_url.rstrip("/")
        self.identifier = identifier
        self.password = password
        self.market = market
        self._token = ""
        self._lock = threading.Lock()

    def login(self) -> None:
        body = json.dumps({"identifier": self.identifier, "password": self.password}).encode()
        request = urllib.request.Request(
            self.base_url + "/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _open_no_redirect(request, DEFAULT_TIMEOUT_SECONDS) as response:
                token = json.load(response).get("access_token")
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            raise RuntimeError("Autenticação técnica falhou; verifique ambiente e credencial.") from None
        if not isinstance(token, str) or not token:
            raise RuntimeError("Autenticação técnica não retornou access token.")
        self._token = token

    def verify_scope(self) -> None:
        request = urllib.request.Request(
            self.base_url + "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            with _open_no_redirect(request, DEFAULT_TIMEOUT_SECONDS) as response:
                identity = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            raise RuntimeError("Não foi possível verificar o escopo do canário.") from None
        if (
            not isinstance(identity, dict)
            or identity.get("active_market") != self.market
            or identity.get("allowed_markets") != [self.market]
            or identity.get("role") != "benchmark_readonly"
            or identity.get("can_approve_tax") is not False
        ):
            raise RuntimeError("Canário sem papel técnico ou vínculo exclusivo do mercado esperado.")

    def get(self, url: str, timeout_seconds: float) -> tuple[Optional[int], Optional[float], Optional[str]]:
        with self._lock:
            if not self._token:
                self.login()
                self.verify_scope()
            token = self._token
        result = make_request(url, {"Authorization": f"Bearer {token}"}, timeout_seconds)
        if result[0] == 401:
            with self._lock:
                if self._token == token:
                    try:
                        self.login()
                        self.verify_scope()
                    except RuntimeError:
                        return 401, None, None
                token = self._token
            return make_request(url, {"Authorization": f"Bearer {token}"}, timeout_seconds)
        return result

    def resolve_fixture_id(self, collection_path: str, code_field: str, code: str) -> str:
        """Descobre UUID pelo código sintético sem expor payload ou ID no relatório."""
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", code):
            raise ValueError("Código de fixture inválido.")
        query = urllib.parse.urlencode({"q": code, "limit": 20})
        request = urllib.request.Request(
            self.base_url + collection_path + "?" + query,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            with _open_no_redirect(request, DEFAULT_TIMEOUT_SECONDS) as response:
                rows = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            raise RuntimeError("Falha ao localizar fixture sintética.") from None
        matches = [row for row in rows if isinstance(row, dict)
                   and row.get(code_field) == code and row.get("market_code") == self.market] if isinstance(rows, list) else []
        if len(matches) != 1:
            raise RuntimeError("Fixture sintética ausente ou ambígua no mercado do canário.")
        try:
            return str(uuid.UUID(str(matches[0]["id"])))
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Fixture sintética sem ID válido.") from None


# ─── Execução de cenário ───────────────────────────────────────────────────────

def run_scenario(
    name: str,
    route_template: str,
    urls: dict[str, str],
    headers: dict[str, str],
    sample_count: int,
    warmup_count: int,
    seed: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    request_fn: Callable | None = None,
    expected_status: int | None = None,
) -> list[SampleResult]:
    """Executa cenário coletando amostras com origens alternadas pelo seed.

    Warmup: warmup_count requisições POR origem (total = warmup_count * n_origens).
    Medição: loop até sample_count amostras 2xx POR origem,
             limitado a MAX_ATTEMPTS_MULTIPLIER * sample_count * n_origens tentativas.
    """
    origins = list(urls.keys())
    request_fn = request_fn or make_request
    n_origins = len(origins)
    results: list[SampleResult] = []

    # Warmup: warmup_count por origem, alternando
    total_warmups = warmup_count * n_origins
    warmup_seq = alternate_origins(origins, total_warmups, seed)
    for seq_idx, origin in enumerate(warmup_seq):
        status, latency, error = request_fn(urls[origin], headers, timeout_seconds)
        results.append(SampleResult(
            route_template=route_template,
            origin=origin,
            latency_ms=latency,
            status_code=status,
            error_type=error,
            sequence=seq_idx,
            is_warmup=True,
            expected_status=expected_status,
        ))

    # Medição: coleta sample_count amostras 2xx por origem
    max_attempts = sample_count * n_origins * MAX_ATTEMPTS_MULTIPLIER
    valid_per_origin: dict[str, int] = {o: 0 for o in origins}
    for attempt_idx in range(max_attempts):
        origin = origins[(seed + attempt_idx) % n_origins]
        status, latency, error = request_fn(urls[origin], headers, timeout_seconds)
        sample = SampleResult(
            route_template=route_template,
            origin=origin,
            latency_ms=latency,
            status_code=status,
            error_type=error,
            sequence=total_warmups + attempt_idx,
            is_warmup=False,
            expected_status=expected_status,
        )
        results.append(sample)
        if sample.is_valid_success:
            valid_per_origin[origin] += 1
        if all(v >= sample_count for v in valid_per_origin.values()):
            break

    return results


def run_scenario_load(
    route_template: str,
    urls: dict[str, str],
    headers: dict[str, str],
    max_workers: int,
    ramp_stages: int,
    requests_per_stage: int,
    warmup_count: int,
    seed: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    request_fn: Callable | None = None,
    expected_status: int | None = None,
) -> list[SampleResult]:
    """Executa cenário de carga com rampa de concorrência.

    Warmup sequencial (warmup_count por origem), depois ramp_stages estágios.
    Workers aumentam linearmente de 1 até max_workers a cada estágio.
    """
    origins = list(urls.keys())
    request_fn = request_fn or make_request
    n_origins = len(origins)
    results: list[SampleResult] = []
    seq = 0

    # Warmup sequencial (igual ao run_scenario)
    total_warmups = warmup_count * n_origins
    warmup_seq = alternate_origins(origins, total_warmups, seed)
    for seq_idx, origin in enumerate(warmup_seq):
        status, latency, error = request_fn(urls[origin], headers, timeout_seconds)
        results.append(SampleResult(
            route_template=route_template,
            origin=origin,
            latency_ms=latency,
            status_code=status,
            error_type=error,
            sequence=seq_idx,
            is_warmup=True,
            expected_status=expected_status,
        ))
    seq = total_warmups

    # Rampa de concorrência por estágios
    for stage in range(ramp_stages):
        workers = max(1, int(max_workers * (stage + 1) / ramp_stages))
        total_stage = requests_per_stage * n_origins
        stage_origins = alternate_origins(origins, total_stage, seed + stage)

        stage_results: list[tuple[SampleResult, int]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(request_fn, urls[stage_origins[i]], headers, timeout_seconds): (stage_origins[i], seq + i)
                for i in range(total_stage)
            }
            for future, (origin, seq_num) in future_map.items():
                status, latency, error = future.result()
                stage_results.append((
                    SampleResult(
                        route_template=route_template,
                        origin=origin,
                        latency_ms=latency,
                        status_code=status,
                        error_type=error,
                        sequence=seq_num,
                        is_warmup=False,
                        expected_status=expected_status,
                    ),
                    seq_num,
                ))

        stage_results.sort(key=lambda x: x[1])
        results.extend(s for s, _ in stage_results)
        seq += total_stage

    return results


# ─── Relatório ─────────────────────────────────────────────────────────────────

def _fmt_ms(value: Optional[float], conclusive: bool, n: int) -> str:
    if value is None:
        return "N/A"
    if not conclusive:
        return f"INCONCLUSIVO (n={n}, precisa >={MIN_SAMPLES_FOR_PERCENTILES})"
    return f"{value:.1f}"


def stats_to_dict(stats: ScenarioStats) -> dict:
    return {
        "name": stats.name,
        "route_template": stats.route_template,
        "origins_tested": stats.origins_tested,
        "sample_count": stats.sample_count,
        "valid_count": stats.valid_count,
        "network_error_count": stats.network_error_count,
        "timeout_count": stats.timeout_count,
        "auth_failure_count": stats.auth_failure_count,
        "client_error_count": stats.client_error_count,
        "functional_failure_count": stats.functional_failure_count,
        "unexpected_status_count": stats.unexpected_status_count,
        "p50_ms": _fmt_ms(stats.p50_ms, True, stats.valid_count),
        "p95_ms": _fmt_ms(stats.p95_ms, stats.p95_conclusive, stats.valid_count),
        "p99_ms": _fmt_ms(stats.p99_ms, stats.p99_conclusive, stats.valid_count),
        "max_ms": f"{stats.max_ms:.1f}" if stats.max_ms is not None else "N/A",
    }


def build_report(
    mode: str,
    all_stats: list[ScenarioStats],
    metadata: dict,
    limitations: list[str],
) -> dict:
    return {
        "meta": {
            **metadata,
            "mode": mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_samples_for_percentiles": MIN_SAMPLES_FOR_PERCENTILES,
        },
        "scenarios": [stats_to_dict(s) for s in all_stats],
        "limitations": limitations,
    }


def determine_exit_code(all_stats: list[ScenarioStats], *, strict_auth: bool = False) -> int:
    """0 = sucesso; 1 = falha funcional, rede total ou ausência de válidas (não-auth).

    Contadores mantidos separados em ScenarioStats para diagnóstico.
    """
    for stats in all_stats:
        if stats.unexpected_status_count or (strict_auth and stats.auth_failure_count):
            return 1
        if stats.functional_failure_count > 0:
            return 1
        if stats.sample_count > 0:
            non_auth_failures = (
                stats.network_error_count
                + stats.timeout_count
                + stats.client_error_count
            )
            if stats.valid_count == 0 and non_auth_failures > 0:
                return 1
    return 0


# ─── Ponto de entrada ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Diagnóstico e benchmark reproduzível da API Ilya.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["smoke", "baseline", "load"], default="smoke")
    parser.add_argument(
        "--target-url",
        default="",
        metavar="URL",
        help="URL base da API Railway (ou use BENCHMARK_TARGET_URL).",
    )
    parser.add_argument(
        "--vercel-url",
        default="",
        metavar="URL",
        help="URL base do Vercel (ou use BENCHMARK_VERCEL_URL).",
    )
    parser.add_argument(
        "--commit",
        default=(os.environ.get("GITHUB_SHA", "") or "")[:8] or "unknown",
    )
    parser.add_argument("--app-version", default=os.environ.get("APP_VERSION", "unknown"))
    parser.add_argument("--environment", default="", metavar="ENV")
    parser.add_argument("--seed", type=int, default=None, metavar="INT")
    parser.add_argument("--output", default="", metavar="FILE")
    parser.add_argument("--load-workers", type=int, default=LOAD_DEFAULT_WORKERS, metavar="N")
    parser.add_argument("--load-stages", type=int, default=LOAD_DEFAULT_STAGES, metavar="N")
    parser.add_argument("--load-requests", type=int, default=LOAD_DEFAULT_REQUESTS_PER_STAGE, metavar="N")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commercial", action="store_true", help="Inclui leituras comerciais com identidade técnica P11.")
    args = parser.parse_args(argv)

    # Lê configuração (precedência: CLI > env var)
    target_url = (args.target_url or os.environ.get("BENCHMARK_TARGET_URL", "")).rstrip("/")
    vercel_url = (args.vercel_url or os.environ.get("BENCHMARK_VERCEL_URL", "")).rstrip("/")
    environment = args.environment or os.environ.get("BENCHMARK_ENVIRONMENT", "unknown")
    seed = args.seed if args.seed is not None else int(os.environ.get("BENCHMARK_SEED", "42"))
    token = os.environ.get("BENCHMARK_API_TOKEN", "")
    canary_identifier = os.environ.get("ILYA_BENCHMARK_USERNAME", "")
    canary_password = os.environ.get("ILYA_BENCHMARK_PASSWORD", "")
    canary_market = os.environ.get("ILYA_BENCHMARK_MARKET", "")
    has_canary = bool(canary_identifier and canary_password and canary_market)
    if any((canary_identifier, canary_password, canary_market)) and not has_canary:
        print("ERRO: identidade técnica P11 está incompleta no ambiente.", file=sys.stderr)
        return 2
    staging_allowlist = os.environ.get("BENCHMARK_STAGING_ALLOWLIST", "")

    if args.commercial and not has_canary:
        print("ERRO: cenários comerciais exigem identidade técnica P11 no ambiente.", file=sys.stderr)
        return 2

    if args.mode == "load":
        # Valida limites de segurança
        if args.load_workers > LOAD_MAX_WORKERS:
            print(f"ERRO: --load-workers {args.load_workers} excede limite {LOAD_MAX_WORKERS}.", file=sys.stderr)
            return 2
        if args.load_stages > LOAD_MAX_STAGES:
            print(f"ERRO: --load-stages {args.load_stages} excede limite {LOAD_MAX_STAGES}.", file=sys.stderr)
            return 2
        if args.load_requests > LOAD_MAX_REQUESTS_PER_STAGE:
            print(f"ERRO: --load-requests {args.load_requests} excede limite {LOAD_MAX_REQUESTS_PER_STAGE}.", file=sys.stderr)
            return 2
        # Política positiva/default-deny
        err = check_load_allowed(target_url, vercel_url, environment, staging_allowlist)
        if err is not None:
            print(f"ERRO: {err}", file=sys.stderr)
            return 2

    if args.dry_run:
        config = {
            "mode": args.mode,
            "has_target_url": bool(target_url),
            "has_vercel_url": bool(vercel_url),
            "environment": environment,
            "seed": seed,
            "has_token": bool(token) or has_canary,
            "commercial": args.commercial,
        }
        print(json.dumps(config, indent=2))
        return 0

    if not target_url:
        print("ERRO: BENCHMARK_TARGET_URL é obrigatório (ou --target-url).", file=sys.stderr)
        return 2

    canary: CanaryAuth | None = None
    if has_canary:
        try:
            if vercel_url:
                vercel_parts = urllib.parse.urlsplit(vercel_url)
                if (vercel_parts.scheme != "https" or not vercel_parts.hostname
                        or vercel_parts.username or vercel_parts.password
                        or vercel_parts.path not in {"", "/"}
                        or vercel_parts.query or vercel_parts.fragment):
                    raise ValueError("Comparação do canário exige origem Vercel HTTPS válida.")
            canary = CanaryAuth(target_url, canary_identifier, canary_password, canary_market)
            canary.login()
            canary.verify_scope()
        except (ValueError, RuntimeError) as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    origins: dict[str, str] = {"railway": target_url}
    if vercel_url:
        origins["vercel"] = vercel_url

    scenarios = select_scenarios(authenticated=bool(token) or canary is not None, commercial=args.commercial)
    if args.commercial and canary is not None:
        details = []
        for spec in FIXTURE_SCENARIOS:
            code = os.environ.get(spec.code_env, "")
            if not code:
                continue
            try:
                fixture_id = canary.resolve_fixture_id(spec.collection_path, spec.code_field, code)
            except (ValueError, RuntimeError) as exc:
                print(f"ERRO: {exc}", file=sys.stderr)
                return 2
            details.append(BenchmarkScenario(
                spec.name, spec.route_template,
                spec.detail_path.format(fixture_id=fixture_id),
            ))
        scenarios += tuple(details)

    sample_count = SMOKE_SAMPLE_COUNT if args.mode == "smoke" else MIN_SAMPLES_FOR_PERCENTILES
    warmup_count = 0 if args.mode == "smoke" else MIN_WARMUP_BASELINE

    all_stats: list[ScenarioStats] = []

    for scenario in scenarios:
        scenario_name, route_template, path = scenario.name, scenario.route_template, scenario.path
        urls = {origin: base + path for origin, base in origins.items()}
        request_fn = (
            (lambda url, _headers, timeout: canary.get(url, timeout))
            if scenario.requires_auth and canary is not None else make_request
        )

        if args.mode == "load":
            samples = run_scenario_load(
                route_template=route_template,
                urls=urls,
                headers=headers,
                max_workers=args.load_workers,
                ramp_stages=args.load_stages,
                requests_per_stage=args.load_requests,
                warmup_count=warmup_count,
                seed=seed,
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                request_fn=request_fn,
                expected_status=scenario.expected_status,
            )
        else:
            samples = run_scenario(
                name=scenario_name,
                route_template=route_template,
                urls=urls,
                headers=headers,
                sample_count=sample_count,
                warmup_count=warmup_count,
                seed=seed,
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                request_fn=request_fn,
                expected_status=scenario.expected_status,
            )

        # Estatísticas separadas por origem
        for origin_name in origins:
            origin_samples = [s for s in samples if s.origin == origin_name]
            stats = compute_stats(
                f"{scenario_name}_{origin_name}",
                route_template,
                origin_samples,
            )
            all_stats.append(stats)

    limitations: list[str] = []
    if args.mode == "smoke":
        limitations.append(
            f"Modo smoke: {SMOKE_SAMPLE_COUNT} amostras por origem — "
            f"p95/p99 são inconclusivos (necessário >={MIN_SAMPLES_FOR_PERCENTILES})."
        )
    if not token and canary is None:
        limitations.append(
            "Sem credencial: apenas rotas públicas testadas. "
            "401 de rotas autenticadas não são operação comercial válida."
        )
    if not vercel_url:
        limitations.append("Sem URL Vercel: comparação Railway/Vercel indisponível.")

    metadata = {
        "commit": args.commit,
        "app_version": args.app_version,
        "environment": environment,
        "seed": seed,
        "tool": "benchmark_production_api",
        "tool_version": "2.0.0",
    }

    report = build_report(args.mode, all_stats, metadata, limitations)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(report_json, encoding="utf-8")
        print(f"Relatório gravado em: {args.output}", file=sys.stderr)
    else:
        print(report_json)

    return determine_exit_code(all_stats, strict_auth=args.commercial)


if __name__ == "__main__":
    sys.exit(main())
