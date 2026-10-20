"""Testes unitários de contrato do gerador de carga e orçamento de conexões (P13)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ops.load import load_generator as lg  # noqa: E402
from ops.load import pool_metrics_probe as pmp  # noqa: E402

TARGET = "https://staging.example.invalid"
METRICS_SECRET = "metrics-secret-value-for-tests"


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _metrics_text(*, in_use: int = 2, timeouts: int | None = 0, workers: str = "1", start: str = "1.79e+09") -> str:
    lines = [
        "# TYPE ilya_db_pool_timeouts_total counter",
        f'ilya_app_info{{version="1.0",workers="{workers}"}} 1',
        f"ilya_process_start_time_seconds {start}",
        f'ilya_db_pool_connections{{state="in_use"}} {in_use}',
        'ilya_db_pool_connections{state="available"} 8',
    ]
    if timeouts is not None:
        lines.append(f'ilya_db_pool_timeouts_total{{pool="primary"}} {timeouts}')
    return "\n".join(lines + ["# EOF"]) + "\n"


@pytest.fixture
def network_calls(monkeypatch):
    """Toda abertura urllib (canário, scrape, carga) é registrada e falha."""
    calls: list[str] = []

    def _open(self, request, *args, **kwargs):
        calls.append(getattr(request, "full_url", str(request)))
        raise AssertionError("rede aberta durante teste offline")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _open)
    return calls


@pytest.fixture
def load_env(monkeypatch):
    monkeypatch.setenv("BENCHMARK_TARGET_URL", TARGET)
    monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
    monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "staging.example.invalid")
    monkeypatch.setenv("ILYA_BENCHMARK_USERNAME", "bench-br")
    monkeypatch.setenv("ILYA_BENCHMARK_PASSWORD", "not-a-real-secret")
    monkeypatch.setenv("ILYA_BENCHMARK_MARKET", "BR")
    monkeypatch.setenv("ILYA_BENCHMARK_METRICS_TOKEN", METRICS_SECRET)
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)


class FakeCanary:
    instances: list["FakeCanary"] = []

    def __init__(self, *_args) -> None:
        self.calls: list[str] = []
        FakeCanary.instances.append(self)

    def login(self) -> None:
        self.calls.append("login")

    def verify_scope(self) -> None:
        self.calls.append("verify_scope")

    def get(self, url, _timeout):
        self.calls.append(url)
        return 200, 10.0, None


def test_default_constants():
    assert lg.DEFAULT_STAGE_USERS == (1, 5, 10, 20)
    assert lg.CONDITIONAL_STAGE_40_USERS == 40
    assert lg.DEFAULT_WARMUP_SECONDS == 60.0
    assert lg.DEFAULT_STAGE_DURATION_SECONDS == 300.0


def test_build_scenario_mix_with_directories():
    mix = lg.build_scenario_mix(include_directories=True, postal_mode="simulated")
    assert mix.total_weight == 100
    assert mix.effective_shares == {
        "products": 35.0,
        "orders": 25.0,
        "dashboard": 15.0,
        "directories": 15.0,
        "postal": 10.0,
    }


def test_build_scenario_mix_without_directories():
    mix = lg.build_scenario_mix(include_directories=False, postal_mode="simulated")
    assert mix.total_weight == 85
    assert "directories" not in mix.effective_shares
    limitations_text = " ".join(mix.limitations)
    assert "benchmark_readonly" in limitations_text


def test_build_scenario_mix_postal_simulated():
    mix = lg.build_scenario_mix(postal_mode="simulated")
    postal = next(item for item in mix.scenarios if item.category == "postal")
    assert postal.simulated_only is True


def test_connection_budget_single_replica():
    budget = lg.calculate_connection_budget(
        replicas=1,
        web_concurrency=1,
        db_pool_size=5,
        db_max_overflow=5,
        reserved_connections=10,
    )
    assert budget.api_max_connections == 10
    assert budget.total_required_connections == 20
    assert budget.safe_connection_ceiling == 85
    assert budget.is_within_budget is True


def test_connection_budget_two_by_two_redis():
    budget = lg.calculate_connection_budget(
        replicas=2,
        web_concurrency=2,
        rate_limit_storage_uri="redis://localhost:6379/0",
    )
    assert budget.api_max_connections == 40
    assert budget.total_required_connections == 50
    assert budget.is_within_budget is True


def test_connection_budget_two_by_two_memory_rejected():
    budget = lg.calculate_connection_budget(
        replicas=2,
        web_concurrency=2,
        rate_limit_storage_uri="memory://",
    )
    assert budget.is_within_budget is False
    assert any("RATE_LIMIT_STORAGE_URI" in err for err in budget.validation_errors)


def test_connection_budget_two_by_four_exceeds_safe_ceiling():
    budget = lg.calculate_connection_budget(
        replicas=2,
        web_concurrency=4,
        rate_limit_storage_uri="redis://localhost:6379/0",
    )
    assert budget.api_max_connections == 80
    assert budget.total_required_connections == 90
    assert budget.total_required_connections > budget.safe_connection_ceiling
    assert budget.is_within_budget is False


def _make_sample(
    seq: int = 0,
    *,
    status_code: int | None = 200,
    latency_ms: float | None = 10.0,
    error_type: str | None = None,
    ts: float | None = None,
    is_warmup: bool = False,
) -> lg.SampleResult:
    return lg.TimedSample(
        route_template="GET /products",
        origin="railway",
        latency_ms=latency_ms,
        status_code=status_code,
        error_type=error_type,
        sequence=seq,
        is_warmup=is_warmup,
        expected_status=200,
        monotonic_s=ts,
    )


def _budget() -> lg.ConnectionBudget:
    return lg.calculate_connection_budget(
        replicas=1,
        web_concurrency=1,
        db_pool_size=5,
        db_max_overflow=5,
        reserved_connections=10,
    )


def test_abort_error_rate_exceeded():
    samples = [_make_sample(i, status_code=400, ts=10.0 + i) for i in range(10)] + [
        _make_sample(10 + i, status_code=200, ts=20.0 + i) for i in range(90)
    ]
    result = lg.evaluate_abort_condition(
        samples,
        baseline_p95_ms=100.0,
        budget=_budget(),
        evaluation_duration_seconds=120.0,
        now=120.0,
    )
    assert result is not None
    assert result.code == "error_rate_exceeded"


# ─── R03: janela deslizante monotônica ─────────────────────────────────────────

def _evaluate_window(samples, *, now: float, sustained: float):
    return lg.evaluate_abort_condition(
        samples,
        baseline_p95_ms=None,
        max_p95_ms=10_000.0,
        budget=_budget(),
        evaluation_duration_seconds=sustained,
        now=now,
    )


def test_error_window_old_failures_leave_window():
    # 50% de erro nos primeiros 60 s, depois 340 s limpos: média histórica > 5%,
    # mas a janela [280, 400] só tem sucessos.
    samples = [_make_sample(i, status_code=429 if i % 2 else 200, ts=float(i)) for i in range(60)]
    samples += [_make_sample(60 + i, ts=60.0 + i) for i in range(341)]
    cumulative_errors = sum(1 for s in samples if not s.is_valid_success) / len(samples)
    assert cumulative_errors > 0.05
    assert _evaluate_window(samples, now=400.0, sustained=400.0) is None


def test_error_window_recent_burst_triggers():
    samples = [_make_sample(i, ts=float(i)) for i in range(380)]
    samples += [_make_sample(380 + i, status_code=429, ts=380.0 + i) for i in range(20)]
    result = _evaluate_window(samples, now=400.0, sustained=400.0)
    assert result is not None
    assert result.code == "error_rate_exceeded"
    assert "/120" in result.message  # janela, não o total histórico


def test_error_window_needs_full_120s_after_warmup():
    samples = [_make_sample(i, status_code=429, ts=float(i)) for i in range(5)]
    samples += [_make_sample(5 + i, ts=5.0 + i) for i in range(40)]
    assert _evaluate_window(samples, now=119.0, sustained=119.9) is None


def test_error_window_ignores_warmup_samples():
    warm = [_make_sample(i, status_code=429, ts=float(i), is_warmup=True) for i in range(100)]
    hot = [_make_sample(100 + i, ts=100.0 + i) for i in range(121)]
    assert _evaluate_window(warm + hot, now=220.0, sustained=120.0) is None


def test_error_window_insufficient_traffic_is_inconclusive():
    samples = [_make_sample(i, status_code=429 if i < 5 else 200, ts=float(i)) for i in range(19)]
    assert _evaluate_window(samples, now=120.0, sustained=120.0) is None


def test_error_window_requires_monotonic_now_and_timestamps():
    timed = [_make_sample(i, ts=float(i)) for i in range(30)]
    with pytest.raises(ValueError):
        lg.evaluate_abort_condition(
            timed, baseline_p95_ms=100.0, budget=_budget(), evaluation_duration_seconds=120.0
        )
    untimed = [_make_sample(i) for i in range(30)]
    with pytest.raises(ValueError):
        _evaluate_window(untimed, now=120.0, sustained=120.0)


def test_abort_p95_absolute_ceiling_without_baseline():
    samples = [_make_sample(i, latency_ms=900.0) for i in range(20)]
    result = lg.evaluate_abort_condition(
        samples, baseline_p95_ms=None, max_p95_ms=500.0, budget=_budget()
    )
    assert result is not None
    assert result.code == "p95_absolute_ceiling"


def _run_stage(clock: FakeClock, *, auth_fn, probe=lambda: (1, 0), warmup=10.0, duration=200.0):
    return lg.run_stage_samples(
        stage_label="A",
        virtual_users=1,
        target_url=TARGET,
        mix=lg.build_scenario_mix(),
        warmup_seconds=warmup,
        stage_duration_seconds=duration,
        pacing_seconds=1.0,
        seed=7,
        budget=_budget(),
        metrics_probe_fn=probe,
        max_p95_ms=10_000.0,
        auth_request_fn=auth_fn,
        public_request_fn=lambda *_a: (_ for _ in ()).throw(AssertionError("rede pública")),
        clock=clock,
        sleep=clock.sleep,
    )


def test_run_stage_warmup_errors_not_mixed_into_window():
    clock = FakeClock()
    t0 = clock.t

    def auth_fn(_url, _timeout):
        return (503, 10.0, None) if clock.t - t0 < 60.0 else (200, 10.0, None)

    samples, report = _run_stage(clock, auth_fn=auth_fn, warmup=60.0, duration=130.0)
    assert report.aborted is False
    assert report.error_rate == 0.0
    assert all(isinstance(s, lg.TimedSample) and s.monotonic_s is not None for s in samples)


def test_run_stage_recent_burst_aborts_with_fake_clock():
    clock = FakeClock()
    t0 = clock.t

    def auth_fn(_url, _timeout):
        return (429, 10.0, None) if clock.t - t0 >= 10.0 + 150.0 else (200, 10.0, None)

    samples, report = _run_stage(clock, auth_fn=auth_fn)
    assert report.aborted is True
    assert report.abort_reason["code"] == "error_rate_exceeded"
    assert samples[-1].monotonic_s - t0 > 160.0
    assert samples[-1].monotonic_s - t0 < 10.0 + 200.0


def test_run_stage_keeps_scenarios_with_same_route_separate():
    clock = FakeClock()
    mix = lg.ScenarioMix(
        scenarios=(
            lg.WeightedScenario(lg.BenchmarkScenario("products_without_total", "GET /products", "/products?include_total=false", requires_auth=False), 1, "products"),
            lg.WeightedScenario(lg.BenchmarkScenario("products_with_total", "GET /products", "/products?include_total=true", requires_auth=False), 1, "products"),
        ),
        total_weight=2,
        effective_shares={"products": 100.0},
    )
    samples, report = lg.run_stage_samples(
        stage_label="A", virtual_users=1, target_url=TARGET, mix=mix,
        warmup_seconds=0.0, stage_duration_seconds=100.0, pacing_seconds=1.0,
        seed=7, budget=_budget(), metrics_probe_fn=lambda: (1, 0),
        max_p95_ms=10_000.0, public_request_fn=lambda *_: (200, 10.0, None),
        clock=clock, sleep=clock.sleep,
    )
    counts = {item["name"]: item["sample_count"] for item in report.scenario_stats}
    assert set(counts) == {"products_without_total", "products_with_total"}
    assert all(count > 0 for count in counts.values())
    assert sum(counts.values()) == len(samples) == report.total_requests


# ─── R02: probe de pool ────────────────────────────────────────────────────────

def test_parse_pool_metrics_valid_and_lazy_timeout_counter():
    snap = pmp.parse_pool_metrics(_metrics_text(in_use=3, timeouts=None))
    assert snap.in_use == 3
    assert snap.pool_timeouts_total == 0
    assert snap.workers_label == "1"


@pytest.mark.parametrize(
    "text",
    [
        "",
        _metrics_text().replace('ilya_db_pool_connections{state="in_use"} 2\n', ""),
        _metrics_text() + 'ilya_db_pool_connections{state="in_use"} 4\n',
        _metrics_text().replace("ilya_process_start_time_seconds 1.79e+09\n", ""),
        _metrics_text().replace('workers="1"', 'version2="x"'),
        _metrics_text(in_use=2).replace('{state="in_use"} 2', '{state="in_use"} NaN'),
        _metrics_text(in_use=2).replace('{state="in_use"} 2', '{state="in_use"} 2.5'),
    ],
)
def test_parse_pool_metrics_rejects_missing_or_invalid(text):
    with pytest.raises(pmp.MetricsProbeError):
        pmp.parse_pool_metrics(text)


def test_metrics_coverage_only_single_process():
    assert pmp.check_metrics_coverage(replicas=1, web_concurrency=1) is None
    assert pmp.check_metrics_coverage(replicas=1, web_concurrency=2) is not None
    assert pmp.check_metrics_coverage(replicas=2, web_concurrency=1) is not None


@pytest.mark.parametrize("path", ["internal/metrics", "//evil.example/m", "/m?x=1", "/m#f", "/@evil", "/a\\b"])
def test_build_metrics_url_rejects_host_changes(path):
    with pytest.raises(ValueError):
        pmp.build_metrics_url(TARGET, path)


def test_build_metrics_url_same_host():
    assert pmp.build_metrics_url(TARGET + "/", "/internal/metrics") == TARGET + "/internal/metrics"


def test_probe_requires_prime_and_reports_timeout_delta():
    clock = FakeClock()
    texts = iter([_metrics_text(in_use=1, timeouts=4), _metrics_text(in_use=6, timeouts=5)])
    probe = pmp.PoolPressureProbe(lambda: next(texts), expected_workers=1, min_interval_seconds=5.0, clock=clock)
    with pytest.raises(pmp.MetricsProbeError):
        probe()
    probe.prime()
    assert probe() == (1, 0)  # dentro do intervalo: valor em cache, sem scrape
    assert probe.scrape_count == 1
    clock.sleep(5.0)
    assert probe() == (6, 1)
    assert probe.scrape_count == 2


def test_probe_rejects_workers_mismatch():
    probe = pmp.PoolPressureProbe(lambda: _metrics_text(workers="unknown"), expected_workers=1)
    with pytest.raises(pmp.MetricsProbeError):
        probe.prime()


@pytest.mark.parametrize(
    "second",
    [
        _metrics_text(timeouts=0, start="1.80e+09"),  # processo trocado
        _metrics_text(timeouts=1),  # contador regrediu (baseline=3)
    ],
)
def test_probe_detects_process_change(second):
    clock = FakeClock()
    texts = iter([_metrics_text(timeouts=3), second])
    probe = pmp.PoolPressureProbe(lambda: next(texts), expected_workers=1, min_interval_seconds=0.0, clock=clock)
    probe.prime()
    with pytest.raises(pmp.MetricsProbeError):
        probe()


def test_probe_transport_failure_is_never_zero():
    def boom():
        raise ConnectionResetError("detalhe interno")

    probe = pmp.PoolPressureProbe(boom, expected_workers=1)
    with pytest.raises(pmp.MetricsProbeError) as info:
        probe.prime()
    assert "detalhe interno" not in str(info.value)


def test_fetch_metrics_text_hides_credential_on_http_error(monkeypatch):
    seen = {}

    def _open(request, timeout):
        seen["auth"] = request.get_header("Authorization")
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(pmp._OPENER, "open", _open)
    with pytest.raises(pmp.MetricsProbeError) as info:
        pmp.fetch_metrics_text(TARGET + "/internal/metrics", METRICS_SECRET, 1.0)
    assert seen["auth"] == f"Bearer {METRICS_SECRET}"
    assert METRICS_SECRET not in str(info.value)
    assert "404" in str(info.value)


@pytest.mark.parametrize(
    "probe, expected_code",
    [
        (lambda: (_ for _ in ()).throw(pmp.MetricsProbeError("scrape indisponível")), "metrics_probe_failed"),
        (lambda: None, "metrics_probe_failed"),
        (lambda: (1, -1), "metrics_probe_failed"),
        (lambda: (1, 1), "pool_timeout"),
        (lambda: (85, 0), "db_connection_ceiling"),
    ],
)
def test_run_stage_precheck_blocks_requests(probe, expected_code):
    clock = FakeClock()
    calls: list[str] = []

    def auth_fn(url, _timeout):
        calls.append(url)
        return 200, 10.0, None

    samples, report = _run_stage(clock, auth_fn=auth_fn, probe=probe)
    assert report.aborted is True
    assert report.abort_reason["code"] == expected_code
    assert samples == []
    assert calls == []


def test_run_stage_probe_failure_mid_stage_aborts():
    clock = FakeClock()
    t0 = clock.t

    def probe():
        if clock.t - t0 >= 30.0:
            raise pmp.MetricsProbeError("Scrape de métricas respondeu 503.")
        return (2, 0)

    samples, report = _run_stage(clock, auth_fn=lambda *_a: (200, 10.0, None), probe=probe)
    assert report.aborted is True
    assert report.abort_reason == {"code": "metrics_probe_failed", "message": "Scrape de métricas respondeu 503."}
    assert samples[-1].monotonic_s - t0 < 32.0
    assert report.peak_db_connections_in_use == 2


# ─── R01/R02: CLI fail-closed ──────────────────────────────────────────────────

def test_validate_latency_guard():
    assert lg.validate_latency_guard(None, None) is not None
    assert lg.validate_latency_guard(0.0, None) is not None
    assert lg.validate_latency_guard(float("nan"), 500.0) is not None
    assert lg.validate_latency_guard(None, float("inf")) is not None
    assert lg.validate_latency_guard(-1.0, None) is not None
    assert lg.validate_latency_guard(120.0, None) is None
    assert lg.validate_latency_guard(None, 800.0) is None
    assert lg.effective_p95_limit_ms(120.0, 500.0) == 500.0
    assert lg.effective_p95_limit_ms(80.0, 500.0) == 400.0


def test_main_without_latency_limit_refuses_before_network(load_env, network_calls, monkeypatch):
    FakeCanary.instances = []
    fetches: list[str] = []
    monkeypatch.setattr(lg, "CanaryAuth", FakeCanary)
    monkeypatch.setattr(lg, "fetch_metrics_text", lambda *a: fetches.append(a[0]) or _metrics_text())
    assert lg.main([]) == 2
    assert network_calls == []
    assert FakeCanary.instances == []
    assert fetches == []


@pytest.mark.parametrize("flag", ["--baseline-p95-ms", "--max-p95-ms"])
@pytest.mark.parametrize("value", ["0", "-5", "nan", "inf"])
def test_main_rejects_invalid_latency_limit(load_env, network_calls, flag, value):
    assert lg.main([flag, value]) == 2
    assert network_calls == []


def test_main_dry_run_without_baseline_is_offline_and_not_authorization(network_calls, capsys):
    assert lg.main(["--dry-run"]) == 0
    captured = capsys.readouterr()
    plan = json.loads(captured.out)
    assert plan["load_preconditions"] == {
        "latency_limit_ok": False,
        "pool_metrics_coverage_ok": True,
        "allowlist_status": "unverified",
        "dry_run_authorizes_load": False,
    }
    assert "não autoriza carga" in captured.err
    assert network_calls == []


def test_dry_run_validates_supplied_target_allowlist_offline(load_env, network_calls, capsys):
    assert lg.main(["--dry-run", "--target-url", "https://unlisted.example.invalid"]) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["load_preconditions"]["allowlist_status"] == "blocked"
    assert lg.main(["--dry-run", "--target-url", TARGET]) == 0
    allowed = json.loads(capsys.readouterr().out)
    assert allowed["load_preconditions"]["allowlist_status"] == "allowed"
    assert network_calls == []


@pytest.mark.parametrize(
    "extra_args, env_overrides",
    [
        (["--web-concurrency", "2"], {"RATE_LIMIT_STORAGE_URI": "redis://cache.invalid:6379/0"}),
        (["--replicas", "2"], {"RATE_LIMIT_STORAGE_URI": "redis://cache.invalid:6379/0"}),
        ([], {"ILYA_BENCHMARK_METRICS_TOKEN": ""}),
        (["--metrics-path", "//evil.example/metrics"], {}),
        (["--metrics-timeout-seconds", "0"], {}),
    ],
)
def test_main_refuses_without_full_pool_coverage(load_env, network_calls, monkeypatch, extra_args, env_overrides):
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)
    FakeCanary.instances = []
    monkeypatch.setattr(lg, "CanaryAuth", FakeCanary)
    assert lg.main(["--max-p95-ms", "800", *extra_args]) == 2
    assert network_calls == []
    assert FakeCanary.instances == []


def test_main_probe_prime_failure_refuses_load(load_env, network_calls, monkeypatch):
    FakeCanary.instances = []
    monkeypatch.setattr(lg, "CanaryAuth", FakeCanary)

    def failing_fetch(*_a):
        raise pmp.MetricsProbeError("Scrape de métricas respondeu 404.")

    monkeypatch.setattr(lg, "fetch_metrics_text", failing_fetch)
    stage_calls: list[dict] = []
    monkeypatch.setattr(lg, "run_stage_samples", lambda **kw: stage_calls.append(kw))
    assert lg.main(["--max-p95-ms", "800"]) == 2
    assert stage_calls == []
    assert FakeCanary.instances == []  # prime falha antes do login
    assert network_calls == []


def test_main_valid_path_injects_probe_and_keeps_limits(load_env, network_calls, monkeypatch, tmp_path):
    FakeCanary.instances = []
    monkeypatch.setattr(lg, "CanaryAuth", FakeCanary)
    fetched: list[tuple] = []
    monkeypatch.setattr(lg, "fetch_metrics_text", lambda *a: fetched.append(a) or _metrics_text(in_use=1))
    stage_kwargs: list[dict] = []

    def fake_stage(**kw):
        stage_kwargs.append(kw)
        assert kw["metrics_probe_fn"]() == (1, 0)
        return [], lg.StageReport(
            stage_label=kw["stage_label"], virtual_users=kw["virtual_users"], duration_seconds=1.0,
            total_requests=0, valid_requests=0, error_rate=0.0, requests_per_second=0.0,
            scenario_stats=[], aborted=False, peak_db_connections_in_use=1, pool_timeouts_since_start=0,
        )

    monkeypatch.setattr(lg, "run_stage_samples", fake_stage)
    output = tmp_path / "p13.json"
    code = lg.main(["--baseline-p95-ms", "120", "--max-p95-ms", "500", "--output", str(output)])
    assert code == 0
    assert network_calls == []
    assert fetched and fetched[0][0] == TARGET + "/internal/metrics"
    assert fetched[0][1] == METRICS_SECRET
    assert len(stage_kwargs) == len(lg.DEFAULT_STAGE_USERS)
    assert all(kw["baseline_p95_ms"] == 120.0 and kw["max_p95_ms"] == 500.0 for kw in stage_kwargs)
    assert all(isinstance(kw["metrics_probe_fn"], pmp.PoolPressureProbe) for kw in stage_kwargs)

    raw = output.read_text(encoding="utf-8")
    assert METRICS_SECRET not in raw
    assert "token" not in raw.lower()
    report = json.loads(raw)
    criteria = report["plan"]["abort_criteria"]
    assert criteria["baseline_p95_ms"] == 120.0
    assert criteria["max_p95_ms"] == 500.0
    assert criteria["effective_p95_limit_ms"] == 500.0
    assert report["stages"][0]["pool_timeouts_since_start"] == 0


def test_abort_p95_degradation():
    samples = [_make_sample(i, latency_ms=1000.0) for i in range(20)]
    result = lg.evaluate_abort_condition(
        samples,
        baseline_p95_ms=100.0,
        budget=_budget(),
        evaluation_duration_seconds=10.0,
    )
    assert result is not None
    assert result.code == "p95_degradation"


def test_abort_unavailability():
    samples = [_make_sample(i, status_code=503) for i in range(10)]
    result = lg.evaluate_abort_condition(
        samples,
        baseline_p95_ms=100.0,
        budget=_budget(),
        evaluation_duration_seconds=10.0,
    )
    assert result is not None
    assert result.code == "unavailability"


def test_abort_db_connection_ceiling():
    budget = _budget()
    result = lg.evaluate_abort_condition(
        [_make_sample()],
        baseline_p95_ms=100.0,
        budget=budget,
        observed_db_connections=budget.safe_connection_ceiling,
        evaluation_duration_seconds=10.0,
    )
    assert result is not None
    assert result.code == "db_connection_ceiling"


def test_abort_pool_timeout():
    result = lg.evaluate_abort_condition(
        [_make_sample()],
        baseline_p95_ms=100.0,
        budget=_budget(),
        observed_pool_timeouts=1,
        evaluation_duration_seconds=10.0,
    )
    assert result is not None
    assert result.code == "pool_timeout"


def test_main_dry_run_returns_zero_and_no_secrets(capsys):
    exit_code = lg.main(["--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload).lower()
    assert "password" not in serialized
    assert "token" not in serialized


def test_main_rejects_production_environment(monkeypatch, network_calls, capsys):
    monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "staging.example.invalid")
    exit_code = lg.main(
        ["--environment", "producao", "--target-url", "https://staging.example.invalid", "--max-p95-ms", "800"]
    )
    assert exit_code == 2
    assert "staging/homologacao" in capsys.readouterr().err
    assert network_calls == []


def test_main_rejects_railway_host(monkeypatch, network_calls, capsys):
    monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "app.up.railway.app")
    exit_code = lg.main(
        ["--environment", "homologacao", "--target-url", "https://app.up.railway.app", "--max-p95-ms", "800"]
    )
    assert exit_code == 2
    assert "up.railway.app" in capsys.readouterr().err
    assert network_calls == []


def test_main_password_argument_not_supported():
    with pytest.raises(SystemExit):
        lg.main(["--password", "secret"])
