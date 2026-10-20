"""Testes unitários de contrato do gerador de carga e orçamento de conexões (P13)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ops.load import load_generator as lg  # noqa: E402


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
) -> lg.SampleResult:
    return lg.SampleResult(
        route_template="GET /products",
        origin="railway",
        latency_ms=latency_ms,
        status_code=status_code,
        error_type=error_type,
        sequence=seq,
        is_warmup=False,
        expected_status=200,
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
    samples = [_make_sample(i, status_code=400) for i in range(10)] + [
        _make_sample(10 + i, status_code=200) for i in range(90)
    ]
    result = lg.evaluate_abort_condition(
        samples,
        baseline_p95_ms=100.0,
        budget=_budget(),
        evaluation_duration_seconds=120.0,
    )
    assert result is not None
    assert result.code == "error_rate_exceeded"


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


def test_main_rejects_production_environment(monkeypatch):
    monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "staging.example.invalid")
    exit_code = lg.main(
        ["--environment", "producao", "--target-url", "https://staging.example.invalid"]
    )
    assert exit_code == 2


def test_main_rejects_railway_host(monkeypatch):
    monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "app.up.railway.app")
    exit_code = lg.main(
        ["--environment", "homologacao", "--target-url", "https://app.up.railway.app"]
    )
    assert exit_code == 2


def test_main_password_argument_not_supported():
    with pytest.raises(SystemExit):
        lg.main(["--password", "secret"])
