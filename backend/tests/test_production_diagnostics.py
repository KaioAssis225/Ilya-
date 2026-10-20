"""Testes unitários da ferramenta de diagnóstico e benchmark (P04).

Critérios de aceite originais:
  1. Erros de rede são separados da distribuição de latência.
  2. 3 amostras produzem p95/p99 inconclusivos.
  3. 30 amostras produzem percentis determinísticos.
  4. Alternância de origens Railway/Vercel é determinística por seed.
  5. Cabeçalhos sensíveis são redactados antes de qualquer saída.
  6. Código de saída 1 quando há falha funcional (5xx); 0 sem falha.

Regressões de segurança (P04 rev2):
  7.  valid_count e percentis usam apenas 2xx; 401/403/4xx/5xx excluídos.
  8.  Modo load bloqueado sem staging/homologacao + allowlist explícita.
  9.  .up.railway.app, URLs fora da allowlist e ambientes não-staging bloqueados.
  10. Ausência de válidas (não por auth) produz exit 1.
  11. Rede total produz exit 1.
  12. --api-token não existe como argumento de CLI.
  13. Token ausente de dry-run e output.
  14. Estatísticas separadas por origem; 30 válidas por origem no baseline.
  15. Warmup contado por origem; não entra nos percentis.
  16. run_scenario respeita max_attempts e para quando amostra suficiente.
  17. run_scenario_load realiza rampa de concorrência; limites respeitados.
  18. Env vars isolados em todos os testes que chamam main().

Nenhum teste faz requisição de rede real.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest

# ─── Importação via importlib ─────────────────────────────────────────────────

_OPS_DIR = Path(__file__).parent.parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_production_api",
    _OPS_DIR / "benchmark_production_api.py",
)
bpa = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("benchmark_production_api", bpa)
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))
_SPEC.loader.exec_module(bpa)

pytestmark = pytest.mark.unit


# ─── Fixtures de isolamento ───────────────────────────────────────────────────

STAGING_URL = "https://ilya-staging-test.example.com"
STAGING_VERCEL_URL = "https://ilya-staging-vercel.example.com"
# Hostnames usados na allowlist (sem esquema — formato correto para BENCHMARK_STAGING_ALLOWLIST)
STAGING_HOST = "ilya-staging-test.example.com"
STAGING_VERCEL_HOST = "ilya-staging-vercel.example.com"


@pytest.fixture
def clean_env(monkeypatch):
    """Limpa todas BENCHMARK_* para isolamento de testes que chamam main()."""
    for key in (
        "BENCHMARK_TARGET_URL",
        "BENCHMARK_VERCEL_URL",
        "BENCHMARK_API_TOKEN",
        "BENCHMARK_ENVIRONMENT",
        "BENCHMARK_SEED",
        "BENCHMARK_STAGING_ALLOWLIST",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mock_ok(monkeypatch):
    """Mocka make_request para retornar 200 OK sem rede real."""
    def _ok(url, headers, timeout=None):
        return 200, 10.0, None
    monkeypatch.setattr(bpa, "make_request", _ok)


# ─── Auxiliares de amostra ────────────────────────────────────────────────────

def _make_ok(
    latency: float,
    seq: int = 0,
    origin: str = "railway",
    is_warmup: bool = False,
) -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /health/live",
        origin=origin,
        latency_ms=latency,
        status_code=200,
        error_type=None,
        sequence=seq,
        is_warmup=is_warmup,
    )


def _make_network_error(seq: int = 0, origin: str = "railway") -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /health/live",
        origin=origin,
        latency_ms=None,
        status_code=None,
        error_type="network",
        sequence=seq,
        is_warmup=False,
    )


def _make_timeout(seq: int = 0, origin: str = "railway") -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /health/live",
        origin=origin,
        latency_ms=None,
        status_code=None,
        error_type="timeout",
        sequence=seq,
        is_warmup=False,
    )


def _make_auth_failure(latency: float, seq: int = 0, status: int = 401) -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /auth/me",
        origin="railway",
        latency_ms=latency,
        status_code=status,
        error_type=None,
        sequence=seq,
        is_warmup=False,
    )


def _make_server_error(latency: float, seq: int = 0) -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /health/live",
        origin="railway",
        latency_ms=latency,
        status_code=500,
        error_type=None,
        sequence=seq,
        is_warmup=False,
    )


def _make_client_error(latency: float, seq: int = 0, status: int = 404) -> bpa.SampleResult:
    return bpa.SampleResult(
        route_template="GET /health/live",
        origin="railway",
        latency_ms=latency,
        status_code=status,
        error_type=None,
        sequence=seq,
        is_warmup=False,
    )


def _make_stats_simple(
    sample_count: int = 3,
    valid_count: int = 3,
    network_error_count: int = 0,
    timeout_count: int = 0,
    auth_failure_count: int = 0,
    client_error_count: int = 0,
    functional_failures: int = 0,
) -> bpa.ScenarioStats:
    return bpa.ScenarioStats(
        name="s",
        route_template="GET /health/live",
        sample_count=sample_count,
        valid_count=valid_count,
        network_error_count=network_error_count,
        timeout_count=timeout_count,
        auth_failure_count=auth_failure_count,
        client_error_count=client_error_count,
        functional_failure_count=functional_failures,
        p50_ms=50.0 if valid_count > 0 else None,
        p95_ms=50.0 if valid_count > 0 else None,
        p99_ms=50.0 if valid_count > 0 else None,
        max_ms=60.0 if valid_count > 0 else None,
        p95_conclusive=False,
        p99_conclusive=False,
    )


# ─── 1. Erros de rede separados da distribuição ───────────────────────────────

class TestNetworkErrorSeparation:
    def test_erro_de_rede_nao_entra_em_valid_latencies(self):
        samples = [_make_ok(50.0, seq=0), _make_network_error(seq=1), _make_ok(60.0, seq=2)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 2
        assert stats.network_error_count == 1
        assert stats.p50_ms == pytest.approx(55.0)

    def test_timeout_nao_entra_em_valid_latencies(self):
        samples = [_make_ok(40.0, seq=0), _make_timeout(seq=1), _make_ok(80.0, seq=2)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 2
        assert stats.timeout_count == 1
        assert stats.network_error_count == 0

    def test_amostras_so_de_rede_produzem_latencia_nula(self):
        samples = [_make_network_error(seq=i) for i in range(5)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.network_error_count == 5
        assert stats.p50_ms is None
        assert stats.p95_ms is None
        assert stats.max_ms is None

    def test_is_network_error_classifica_corretamente(self):
        assert _make_network_error().is_network_error
        assert _make_timeout().is_network_error
        assert not _make_ok(100.0).is_network_error

    def test_erro_de_rede_nao_e_falha_funcional(self):
        assert not _make_network_error().is_functional_failure


# ─── 2. 3 amostras → p95/p99 inconclusivos ────────────────────────────────────

class TestSmokeSamplesInconclusive:
    def test_3_amostras_p95_inconclusivo(self):
        samples = [_make_ok(float(i), seq=i) for i in range(1, 4)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.sample_count == 3
        assert stats.valid_count == 3
        assert not stats.p95_conclusive
        assert not stats.p99_conclusive

    def test_formato_inconclusivo_contem_contagem_e_minimo(self):
        samples = [_make_ok(float(i), seq=i) for i in range(1, 4)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        d = bpa.stats_to_dict(stats)
        assert "INCONCLUSIVO" in d["p95_ms"]
        assert "n=3" in d["p95_ms"]
        assert str(bpa.MIN_SAMPLES_FOR_PERCENTILES) in d["p95_ms"]

    def test_p50_ainda_calculado_com_3_amostras(self):
        samples = [_make_ok(float(x), seq=i) for i, x in enumerate([10, 20, 30])]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.p50_ms == pytest.approx(20.0)

    @pytest.mark.parametrize("n", [1, 5, 15, 29])
    def test_menos_de_min_samples_e_inconclusivo(self, n: int):
        samples = [_make_ok(float(i), seq=i) for i in range(n)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert not stats.p95_conclusive, f"n={n} deveria ser inconclusivo"


# ─── 3. 30 amostras → percentis determinísticos ───────────────────────────────

class TestBaselinePercentileDeterministic:
    @pytest.fixture
    def stats_30(self) -> bpa.ScenarioStats:
        samples = [_make_ok(float(i), seq=i - 1) for i in range(1, 31)]
        return bpa.compute_stats("s", "GET /health/live", samples)

    def test_30_amostras_sao_conclusivas(self, stats_30):
        assert stats_30.p95_conclusive
        assert stats_30.p99_conclusive
        assert stats_30.valid_count == 30

    def test_p50_deterministico(self, stats_30):
        # [1..30] → index 0.5×29=14.5 → 15.0 + 0.5×1.0 = 15.5
        assert stats_30.p50_ms == pytest.approx(15.5)

    def test_p95_deterministico(self, stats_30):
        # [1..30] → index 0.95×29=27.55 → 28.0 + 0.55×1.0 = 28.55
        assert stats_30.p95_ms == pytest.approx(28.55)

    def test_p99_deterministico(self, stats_30):
        # [1..30] → index 0.99×29=28.71 → 29.0 + 0.71×1.0 = 29.71
        assert stats_30.p99_ms == pytest.approx(29.71)

    def test_max_deterministico(self, stats_30):
        assert stats_30.max_ms == pytest.approx(30.0)

    def test_idempotencia(self):
        samples = [_make_ok(float(i) * 3.7, seq=i) for i in range(30)]
        s1 = bpa.compute_stats("s", "GET /health/live", samples)
        s2 = bpa.compute_stats("s", "GET /health/live", samples)
        assert s1.p50_ms == s2.p50_ms
        assert s1.p95_ms == s2.p95_ms
        assert s1.p99_ms == s2.p99_ms

    def test_warmups_excluidos_da_estatistica(self):
        warmup = [
            bpa.SampleResult("GET /health/live", "railway", 9999.0, 200, None, i, is_warmup=True)
            for i in range(5)
        ]
        real = [_make_ok(float(i), seq=5 + i - 1) for i in range(1, 31)]
        stats = bpa.compute_stats("s", "GET /health/live", warmup + real)
        assert stats.valid_count == 30
        assert stats.p95_ms == pytest.approx(28.55)


# ─── 4. Alternância de origens por seed ───────────────────────────────────────

class TestOriginAlternation:
    def test_alternancia_seed_0(self):
        assert bpa.alternate_origins(["railway", "vercel"], 4, seed=0) == ["railway", "vercel", "railway", "vercel"]

    def test_alternancia_seed_1(self):
        assert bpa.alternate_origins(["railway", "vercel"], 4, seed=1) == ["vercel", "railway", "vercel", "railway"]

    def test_mesma_seed_mesma_sequencia(self):
        a = bpa.alternate_origins(["railway", "vercel"], 10, seed=42)
        b = bpa.alternate_origins(["railway", "vercel"], 10, seed=42)
        assert a == b

    def test_seeds_diferentes_iniciam_em_posicoes_diferentes(self):
        a = bpa.alternate_origins(["railway", "vercel"], 4, seed=0)
        b = bpa.alternate_origins(["railway", "vercel"], 4, seed=1)
        assert a[0] != b[0]

    def test_uma_origem(self):
        assert bpa.alternate_origins(["railway"], 5, seed=99) == ["railway"] * 5

    def test_lista_vazia_levanta_erro(self):
        with pytest.raises(ValueError, match="vazia"):
            bpa.alternate_origins([], 3, seed=0)

    def test_count_zero_retorna_lista_vazia(self):
        assert bpa.alternate_origins(["railway", "vercel"], 0, seed=0) == []

    def test_origins_testadas_excluem_warmups(self):
        samples = [
            bpa.SampleResult("r", "vercel", 50.0, 200, None, 0, is_warmup=True),
            _make_ok(60.0, seq=1, origin="railway"),
        ]
        stats = bpa.compute_stats("s", "r", samples)
        assert stats.origins_tested == ["railway"]


# ─── 5. Redaction de segredos ─────────────────────────────────────────────────

class TestSecretRedaction:
    def test_authorization_redactado(self):
        result = bpa.redact_headers({"Authorization": "Bearer token123"})
        assert result["Authorization"] == "***REDACTED***"

    def test_x_api_key_redactado(self):
        assert bpa.redact_headers({"X-Api-Key": "sk-secret"})["X-Api-Key"] == "***REDACTED***"

    def test_cookie_redactado(self):
        assert bpa.redact_headers({"Cookie": "session=abc"})["Cookie"] == "***REDACTED***"

    def test_cabecalho_publico_nao_redactado(self):
        result = bpa.redact_headers({"Content-Type": "application/json", "Accept": "*/*"})
        assert result["Content-Type"] == "application/json"
        assert result["Accept"] == "*/*"

    def test_redaction_case_insensitive(self):
        result = bpa.redact_headers({"AUTHORIZATION": "t1", "authorization": "t2"})
        for v in result.values():
            assert v == "***REDACTED***"

    def test_headers_vazios(self):
        assert bpa.redact_headers({}) == {}

    def test_preserva_chaves(self):
        headers = {"Authorization": "Bearer s", "Content-Type": "text/plain"}
        assert set(bpa.redact_headers(headers).keys()) == {"Authorization", "Content-Type"}


# ─── 6. Código de saída por falha funcional ───────────────────────────────────

class TestExitCode:
    def test_sem_falha_funcional_retorna_0(self):
        assert bpa.determine_exit_code([_make_stats_simple(functional_failures=0)]) == 0

    def test_com_falha_funcional_retorna_1(self):
        assert bpa.determine_exit_code([_make_stats_simple(functional_failures=1)]) == 1

    def test_qualquer_cenario_com_falha_retorna_1(self):
        stats = [
            _make_stats_simple(functional_failures=0),
            _make_stats_simple(functional_failures=0),
            _make_stats_simple(functional_failures=2),
        ]
        assert bpa.determine_exit_code(stats) == 1

    def test_lista_vazia_retorna_0(self):
        assert bpa.determine_exit_code([]) == 0

    def test_status_5xx_e_falha_funcional(self):
        s = _make_server_error(100.0)
        assert s.is_functional_failure
        assert not s.is_network_error

    def test_status_401_nao_e_falha_funcional(self):
        s = _make_auth_failure(30.0)
        assert not s.is_functional_failure
        assert s.is_auth_failure

    def test_401_contado_em_auth_failure_nao_em_functional(self):
        samples = [_make_auth_failure(30.0, seq=i) for i in range(3)]
        stats = bpa.compute_stats("s", "GET /auth/me", samples)
        assert stats.auth_failure_count == 3
        assert stats.functional_failure_count == 0
        # 401 → valid_count=0, mas apenas auth failures → não dispara exit 1
        assert stats.valid_count == 0
        assert bpa.determine_exit_code([stats]) == 0

    def test_modo_load_bloqueado_em_producao_retorna_2(self, clean_env):
        exit_code = bpa.main(["--mode", "load", "--target-url", "https://ilya-api.railway.app"])
        assert exit_code == 2

    def test_dry_run_retorna_0(self, clean_env):
        assert bpa.main(["--dry-run"]) == 0

    def test_sem_target_url_retorna_2(self, clean_env):
        assert bpa.main(["--mode", "smoke"]) == 2


# ─── 7. valid_count e percentis apenas com 2xx ────────────────────────────────

class TestValidCountOnly2xx:
    def test_401_excluido_de_valid_count(self):
        samples = [_make_auth_failure(30.0, seq=i) for i in range(5)]
        stats = bpa.compute_stats("s", "GET /auth/me", samples)
        assert stats.valid_count == 0
        assert stats.auth_failure_count == 5

    def test_403_excluido_de_valid_count(self):
        samples = [_make_auth_failure(30.0, seq=i, status=403) for i in range(5)]
        stats = bpa.compute_stats("s", "GET /auth/me", samples)
        assert stats.valid_count == 0
        assert stats.auth_failure_count == 5

    def test_5xx_excluido_de_valid_count(self):
        samples = [_make_server_error(50.0, seq=i) for i in range(5)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.functional_failure_count == 5

    def test_4xx_nao_auth_contado_em_client_error(self):
        samples = [_make_client_error(50.0, seq=i, status=404) for i in range(3)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.client_error_count == 3
        assert stats.auth_failure_count == 0

    def test_2xx_incluido_em_valid_count(self):
        samples = [_make_ok(50.0, seq=i) for i in range(10)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 10

    def test_401_nao_contribui_para_percentis(self):
        """Latência de 401 não deve distorcer distribuição."""
        samples = (
            [_make_auth_failure(9999.0, seq=i) for i in range(5)]
            + [_make_ok(50.0, seq=5 + i) for i in range(30)]
        )
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 30
        assert stats.p50_ms == pytest.approx(50.0)

    def test_p95_conclusivo_somente_com_30_validas_nao_tentativas(self):
        """30 tentativas com 20 válidas e 10 erros de rede → inconclusivo."""
        samples = (
            [_make_ok(50.0, seq=i) for i in range(20)]
            + [_make_network_error(seq=20 + i) for i in range(10)]
        )
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 20
        assert not stats.p95_conclusive


# ─── 8–9. Segurança do modo load ─────────────────────────────────────────────

class TestLoadSecurity:
    def test_load_bloqueado_sem_environment_staging(self, clean_env):
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_load_bloqueado_environment_producao(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "producao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_URL)
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_load_bloqueado_sem_allowlist(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_load_bloqueado_allowlist_vazia(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "   ")
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_load_bloqueado_up_railway_app(self, clean_env, monkeypatch):
        url = "https://ilya-api.up.railway.app"
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        # Allowlist em formato hostname correto — garante que o bloqueio é por up.railway.app
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "ilya-api.up.railway.app")
        assert bpa.main(["--mode", "load", "--target-url", url]) == 2

    def test_load_bloqueado_url_nao_na_allowlist(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", "outro.example.com")
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_load_bloqueado_custom_producao_desconhecido(self, clean_env, monkeypatch):
        """Domínio customizado fora da allowlist é bloqueado."""
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main(["--mode", "load", "--target-url", "https://custom-prod.example.com"]) == 2

    def test_load_bloqueado_vercel_url_nao_na_allowlist(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main([
            "--mode", "load",
            "--target-url", STAGING_URL,
            "--vercel-url", "https://nao-na-allowlist.example.com",
        ]) == 2

    def test_check_load_allowed_ambiente_errado(self):
        err = bpa.check_load_allowed(STAGING_URL, "", "producao", STAGING_URL)
        assert err is not None

    def test_check_load_allowed_sem_allowlist(self):
        err = bpa.check_load_allowed(STAGING_URL, "", "homologacao", "")
        assert err is not None
        assert "allowlist" in err.lower()

    def test_check_load_allowed_up_railway_app_bloqueado(self):
        url = "https://ilya.up.railway.app"
        # Allowlist em hostname correto; bloqueio deve ser pelo domínio up.railway.app
        err = bpa.check_load_allowed(url, "", "homologacao", "ilya.up.railway.app")
        assert err is not None
        assert "up.railway.app" in err

    def test_check_load_allowed_url_nao_na_allowlist(self):
        err = bpa.check_load_allowed(STAGING_URL, "", "homologacao", "outro.example.com")
        assert err is not None

    def test_check_load_allowed_permitido(self):
        assert bpa.check_load_allowed(STAGING_URL, "", "homologacao", STAGING_HOST) is None

    def test_check_load_allowed_staging_env(self):
        assert bpa.check_load_allowed(STAGING_URL, "", "staging", STAGING_HOST) is None

    def test_check_load_allowed_vercel_na_allowlist(self):
        allowlist = f"{STAGING_HOST},{STAGING_VERCEL_HOST}"
        assert bpa.check_load_allowed(STAGING_URL, STAGING_VERCEL_URL, "homologacao", allowlist) is None

    # ── Novos testes: validação de URL e formato de allowlist ────────────────

    def test_load_bloqueado_http_scheme(self, clean_env, monkeypatch):
        """target-url com http:// deve ser bloqueado (exige HTTPS)."""
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main(["--mode", "load", "--target-url", f"http://{STAGING_HOST}"]) == 2

    def test_load_bloqueado_userinfo_na_url(self, clean_env, monkeypatch):
        """target-url com userinfo (user:pass@) deve ser bloqueado."""
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        url = f"https://user:pass@{STAGING_HOST}"
        assert bpa.main(["--mode", "load", "--target-url", url]) == 2

    def test_load_bloqueado_query_string_na_url(self, clean_env, monkeypatch):
        """target-url com query string deve ser bloqueado."""
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        url = f"https://{STAGING_HOST}?foo=bar"
        assert bpa.main(["--mode", "load", "--target-url", url]) == 2

    def test_load_bloqueado_allowlist_formato_url(self, clean_env, monkeypatch):
        """Allowlist com URL completa (https://...) deve ser rejeitada."""
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_URL)  # URL, não hostname
        assert bpa.main(["--mode", "load", "--target-url", STAGING_URL]) == 2

    def test_check_load_allowed_http_scheme_bloqueado(self):
        """check_load_allowed rejeita target com scheme http."""
        err = bpa.check_load_allowed(
            f"http://{STAGING_HOST}", "", "homologacao", STAGING_HOST
        )
        assert err is not None
        assert "HTTPS" in err or "https" in err.lower()

    def test_check_load_allowed_userinfo_bloqueado(self):
        """check_load_allowed rejeita target com userinfo."""
        err = bpa.check_load_allowed(
            f"https://user:pass@{STAGING_HOST}", "", "homologacao", STAGING_HOST
        )
        assert err is not None

    def test_check_load_allowed_query_bloqueado(self):
        """check_load_allowed rejeita target com query string."""
        err = bpa.check_load_allowed(
            f"https://{STAGING_HOST}?foo=bar", "", "homologacao", STAGING_HOST
        )
        assert err is not None

    def test_check_load_allowed_fragment_bloqueado(self):
        """check_load_allowed rejeita target com fragmento."""
        err = bpa.check_load_allowed(
            f"https://{STAGING_HOST}#section", "", "homologacao", STAGING_HOST
        )
        assert err is not None

    def test_check_load_allowed_allowlist_formato_url_rejeitado(self):
        """Entrada de allowlist em formato URL (com '://') deve ser rejeitada."""
        err = bpa.check_load_allowed(STAGING_URL, "", "homologacao", STAGING_URL)
        assert err is not None
        assert "://" in err or "esquema" in err.lower() or "URL" in err

    def test_check_load_allowed_host_case_normalizado(self):
        """Allowlist com hostname em maiúsculas deve ser normalizado e aceito."""
        allowlist_upper = STAGING_HOST.upper()
        assert bpa.check_load_allowed(STAGING_URL, "", "homologacao", allowlist_upper) is None

    def test_check_load_allowed_host_trailing_dot_normalizado(self):
        """Allowlist com hostname terminado em ponto deve ser normalizado e aceito."""
        allowlist_dot = STAGING_HOST + "."
        assert bpa.check_load_allowed(STAGING_URL, "", "homologacao", allowlist_dot) is None

    def test_check_load_allowed_target_e_vercel_ambos_permitidos(self):
        """target e vercel_url ambos na allowlist → permitido."""
        allowlist = f"{STAGING_HOST},{STAGING_VERCEL_HOST}"
        result = bpa.check_load_allowed(
            STAGING_URL, STAGING_VERCEL_URL, "homologacao", allowlist
        )
        assert result is None

    def test_check_load_allowed_dominio_custom_nao_listado_bloqueado(self):
        """URL customizada fora da allowlist, mesmo com env correto, é bloqueada."""
        err = bpa.check_load_allowed(
            "https://custom-prod.acme.com", "", "homologacao", STAGING_HOST
        )
        assert err is not None

    def test_load_excede_max_workers_retorna_2(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main([
            "--mode", "load",
            "--target-url", STAGING_URL,
            f"--load-workers={bpa.LOAD_MAX_WORKERS + 1}",
        ]) == 2

    def test_load_excede_max_stages_retorna_2(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main([
            "--mode", "load",
            "--target-url", STAGING_URL,
            f"--load-stages={bpa.LOAD_MAX_STAGES + 1}",
        ]) == 2

    def test_load_excede_max_requests_retorna_2(self, clean_env, monkeypatch):
        monkeypatch.setenv("BENCHMARK_ENVIRONMENT", "homologacao")
        monkeypatch.setenv("BENCHMARK_STAGING_ALLOWLIST", STAGING_HOST)
        assert bpa.main([
            "--mode", "load",
            "--target-url", STAGING_URL,
            f"--load-requests={bpa.LOAD_MAX_REQUESTS_PER_STAGE + 1}",
        ]) == 2


# ─── 10–11. Exit codes: rede total e ausência de válidas ─────────────────────

class TestExitCodeExtended:
    def test_rede_total_exit_1(self):
        samples = [_make_network_error(seq=i) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.network_error_count == 30
        assert bpa.determine_exit_code([stats]) == 1

    def test_timeout_total_exit_1(self):
        samples = [_make_timeout(seq=i) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.timeout_count == 30
        assert bpa.determine_exit_code([stats]) == 1

    def test_5xx_total_exit_1(self):
        samples = [_make_server_error(50.0, seq=i) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.functional_failure_count == 30
        assert bpa.determine_exit_code([stats]) == 1

    def test_4xx_total_sem_auth_exit_1(self):
        """4xx não-auth sem amostras válidas → exit 1."""
        samples = [_make_client_error(50.0, seq=i, status=404) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 0
        assert stats.client_error_count == 30
        assert bpa.determine_exit_code([stats]) == 1

    def test_apenas_401_exit_0(self):
        """Auth failures sem erros não-auth → exit 0 (situação conhecida: sem credencial)."""
        samples = [_make_auth_failure(30.0, seq=i) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /auth/me", samples)
        assert stats.valid_count == 0
        assert stats.auth_failure_count == 30
        assert bpa.determine_exit_code([stats]) == 0

    def test_mix_401_e_200_exit_0(self):
        samples = (
            [_make_auth_failure(30.0, seq=i) for i in range(5)]
            + [_make_ok(50.0, seq=5 + i) for i in range(5)]
        )
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert stats.valid_count == 5
        assert bpa.determine_exit_code([stats]) == 0

    def test_30_tentativas_com_falhas_nao_conclusivas_nao_exit_0(self):
        """30 tentativas sem 1 resposta válida (tudo 503) → exit 1."""
        samples = [_make_server_error(50.0, seq=i) for i in range(30)]
        stats = bpa.compute_stats("s", "GET /health/live", samples)
        assert bpa.determine_exit_code([stats]) == 1


# ─── 12–13. Token: ausência em argv e output ─────────────────────────────────

class TestTokenSecurity:
    def test_api_token_nao_aceito_como_argumento_cli(self, clean_env):
        """--api-token foi removido; argparse deve rejeitar com SystemExit."""
        with pytest.raises(SystemExit):
            bpa.main(["--api-token", "sometoken"])

    def test_dry_run_nao_expoe_valor_do_token(self, clean_env, monkeypatch, capsys):
        monkeypatch.setenv("BENCHMARK_API_TOKEN", "super-secret-token-value")
        bpa.main(["--dry-run"])
        captured = capsys.readouterr()
        assert "super-secret-token-value" not in captured.out
        assert "super-secret-token-value" not in captured.err

    def test_dry_run_indica_presenca_sem_expor_valor(self, clean_env, monkeypatch, capsys):
        monkeypatch.setenv("BENCHMARK_API_TOKEN", "some-token")
        bpa.main(["--dry-run"])
        assert '"has_token": true' in capsys.readouterr().out

    def test_dry_run_nao_expoe_target_url(self, clean_env, monkeypatch, capsys):
        monkeypatch.setenv("BENCHMARK_TARGET_URL", "https://confidential.staging.example.com")
        bpa.main(["--dry-run"])
        assert "confidential.staging.example.com" not in capsys.readouterr().out


# ─── 14–15. Estatísticas por origem e warmup por origem ──────────────────────

class TestPerOriginStats:
    def test_30_validas_por_origem(self):
        railway = [_make_ok(float(i), seq=i, origin="railway") for i in range(30)]
        vercel = [_make_ok(float(i) * 2, seq=30 + i, origin="vercel") for i in range(30)]
        r = bpa.compute_stats("s_r", "GET /live", [s for s in railway + vercel if s.origin == "railway"])
        v = bpa.compute_stats("s_v", "GET /live", [s for s in railway + vercel if s.origin == "vercel"])
        assert r.valid_count == 30
        assert v.valid_count == 30
        assert r.p95_conclusive
        assert v.p95_conclusive

    def test_distribuicoes_nao_agregadas(self):
        """p50 de railway (10ms) e vercel (100ms) permanecem distintos."""
        railway = [_make_ok(10.0, seq=i, origin="railway") for i in range(30)]
        vercel = [_make_ok(100.0, seq=30 + i, origin="vercel") for i in range(30)]
        all_s = railway + vercel
        r = bpa.compute_stats("s", "r", [s for s in all_s if s.origin == "railway"])
        v = bpa.compute_stats("s", "r", [s for s in all_s if s.origin == "vercel"])
        assert r.p50_ms == pytest.approx(10.0)
        assert v.p50_ms == pytest.approx(100.0)

    def test_origins_tested_por_origem(self):
        railway = [_make_ok(50.0, seq=i, origin="railway") for i in range(5)]
        stats = bpa.compute_stats("s", "GET /live", railway)
        assert stats.origins_tested == ["railway"]


# ─── 16. run_scenario: warmup por origem, max_attempts ───────────────────────

class TestRunScenario:
    def test_warmup_por_origem_com_duas_origens(self, monkeypatch):
        """warmup_count=5 × 2 origens → 10 warmup requests totais, 5 por origem."""
        calls: list[str] = []

        def _mock(url, headers, timeout=None):
            calls.append(url)
            return 200, 10.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario(
            name="s", route_template="GET /live",
            urls={"railway": "http://r/live", "vercel": "http://v/live"},
            headers={}, sample_count=3, warmup_count=5, seed=0,
        )
        warmups = [r for r in results if r.is_warmup]
        assert len(warmups) == 10
        assert sum(1 for r in warmups if r.origin == "railway") == 5
        assert sum(1 for r in warmups if r.origin == "vercel") == 5

    def test_para_quando_sample_count_atingido(self, monkeypatch):
        """Para ao atingir sample_count=5 amostras válidas, sem usar max_attempts."""
        call_count = [0]

        def _mock(url, headers, timeout=None):
            call_count[0] += 1
            return 200, 10.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario(
            name="s", route_template="GET /live",
            urls={"railway": "http://r/live"},
            headers={}, sample_count=5, warmup_count=0, seed=0,
        )
        valid = [r for r in results if not r.is_warmup and r.is_valid_success]
        assert len(valid) == 5
        assert call_count[0] <= 5 * 1 * bpa.MAX_ATTEMPTS_MULTIPLIER

    def test_max_attempts_evita_loop_infinito(self, monkeypatch):
        """Quando nenhuma resposta é válida, para em max_attempts."""
        def _fail(url, headers, timeout=None):
            return 503, 10.0, None

        monkeypatch.setattr(bpa, "make_request", _fail)
        results = bpa.run_scenario(
            name="s", route_template="GET /live",
            urls={"railway": "http://r/live"},
            headers={}, sample_count=30, warmup_count=0, seed=0,
        )
        non_warmup = [r for r in results if not r.is_warmup]
        assert len(non_warmup) == 30 * 1 * bpa.MAX_ATTEMPTS_MULTIPLIER
        assert all(not r.is_valid_success for r in non_warmup)


# ─── 17. run_scenario_load: rampa e limites ───────────────────────────────────

class TestRunScenarioLoad:
    def test_emite_requests_em_todos_os_estagios(self, monkeypatch):
        calls: list[str] = []

        def _mock(url, headers, timeout=None):
            calls.append(url)
            return 200, 5.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario_load(
            route_template="GET /live",
            urls={"railway": "http://r/live"},
            headers={},
            max_workers=2, ramp_stages=3, requests_per_stage=5,
            warmup_count=2, seed=0,
        )
        warmups = [r for r in results if r.is_warmup]
        non_warmup = [r for r in results if not r.is_warmup]
        assert len(warmups) == 2         # warmup_count × 1 origem
        assert len(non_warmup) == 15     # 3 estágios × 5 requests × 1 origem

    def test_duas_origens_duas_vezes_requests(self, monkeypatch):
        def _mock(url, headers, timeout=None):
            return 200, 5.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario_load(
            route_template="GET /live",
            urls={"railway": "http://r/live", "vercel": "http://v/live"},
            headers={},
            max_workers=2, ramp_stages=2, requests_per_stage=4,
            warmup_count=2, seed=0,
        )
        warmups = [r for r in results if r.is_warmup]
        non_warmup = [r for r in results if not r.is_warmup]
        assert len(warmups) == 4         # 2 warmups × 2 origens
        assert len(non_warmup) == 16     # 2 estágios × 4 requests × 2 origens

    def test_concorrencia_real_n_threads_simultaneas(self, monkeypatch):
        """Barreira de N workers no estágio único: prova N threads simultâneas sem rede.

        max_workers=4, ramp_stages=1, requests_per_stage=4 → stage 0 tem 4 workers.
        Todos os 4 futures são submetidos de uma vez; todos chegam à barreira(4)
        antes de qualquer um retornar. Se o teste terminar sem BrokenBarrierError,
        4 threads rodaram simultaneamente.
        """
        max_workers_test = 4
        barrier = threading.Barrier(max_workers_test, timeout=5)

        def _mock(url, headers, timeout=None):
            barrier.wait()  # levanta BrokenBarrierError se < max_workers_test simultâneas
            return 200, 5.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario_load(
            route_template="GET /live",
            urls={"railway": "http://r/live"},
            headers={},
            max_workers=max_workers_test,
            ramp_stages=1,
            requests_per_stage=max_workers_test,  # exactly max_workers → preenche o pool
            warmup_count=0,
            seed=0,
        )
        # Se chegou aqui → barreira satisfeita → concorrência real provada
        assert len([r for r in results if not r.is_warmup]) == max_workers_test

    def test_progressao_workers_por_estagio(self, monkeypatch):
        """Prova que workers aumentam de stage 0 para stage 1 (rampa).

        max_workers=4, ramp_stages=2:
          Stage 0: workers = max(1, int(4*1/2)) = 2 → Barrier(2) satisfeito
          Stage 1: workers = max(1, int(4*2/2)) = 4 → Barrier(4) satisfeito

        Stages são sequenciais (stage N+1 só começa após todos os futures do stage N
        completarem), então os índices de chamada separam os stages sem ambiguidade.
        """
        max_workers_test = 4
        ramp_stages = 2
        requests_per_stage = max_workers_test  # 4 por stage, 1 origem

        calls_per_stage = requests_per_stage  # 4

        # Barrier(2) para stage 0; reutilizável (segunda batelada de 2 também satisfaz)
        barrier_s0 = threading.Barrier(2, timeout=5)
        # Barrier(4) para stage 1; todos os 4 workers chegam de uma vez
        barrier_s1 = threading.Barrier(4, timeout=5)

        call_count = [0]
        lock = threading.Lock()

        def _mock(url, headers, timeout=None):
            with lock:
                idx = call_count[0]
                call_count[0] += 1

            if idx < calls_per_stage:
                barrier_s0.wait()
            else:
                barrier_s1.wait()

            return 200, 5.0, None

        monkeypatch.setattr(bpa, "make_request", _mock)
        results = bpa.run_scenario_load(
            route_template="GET /live",
            urls={"railway": "http://r/live"},
            headers={},
            max_workers=max_workers_test,
            ramp_stages=ramp_stages,
            requests_per_stage=requests_per_stage,
            warmup_count=0,
            seed=0,
        )
        # Ambas as barreiras foram satisfeitas sem timeout
        non_warmup = [r for r in results if not r.is_warmup]
        assert len(non_warmup) == ramp_stages * requests_per_stage  # 8 total


# ─── Percentil: casos de borda ────────────────────────────────────────────────

class TestPercentileEdgeCases:
    def test_lista_unitaria(self):
        assert bpa.compute_percentile([42.0], 95) == pytest.approx(42.0)

    def test_lista_vazia_levanta_erro(self):
        with pytest.raises(ValueError, match="vazia"):
            bpa.compute_percentile([], 95)

    def test_p0_retorna_minimo(self):
        assert bpa.compute_percentile([10.0, 20.0, 30.0], 0) == pytest.approx(10.0)

    def test_p100_retorna_maximo(self):
        assert bpa.compute_percentile([10.0, 20.0, 30.0], 100) == pytest.approx(30.0)

    def test_p50_lista_par(self):
        # [10, 20] → index 0.5×1=0.5 → 10 + 0.5×10 = 15.0
        assert bpa.compute_percentile([10.0, 20.0], 50) == pytest.approx(15.0)


# ─── SampleResult: propriedades is_valid_success e is_client_error ───────────

class TestSampleResultProperties:
    @pytest.mark.parametrize("status", [200, 201, 204, 206])
    def test_is_valid_success_2xx(self, status: int):
        s = bpa.SampleResult("r", "railway", 10.0, status, None, 0)
        assert s.is_valid_success

    @pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 422, 500, 503])
    def test_is_valid_success_falso_nao_2xx(self, status: int):
        s = bpa.SampleResult("r", "railway", 10.0, status, None, 0)
        assert not s.is_valid_success

    def test_is_valid_success_falso_rede(self):
        s = bpa.SampleResult("r", "railway", None, None, "network", 0)
        assert not s.is_valid_success

    @pytest.mark.parametrize("status", [400, 404, 422, 429])
    def test_is_client_error_4xx_nao_auth(self, status: int):
        s = bpa.SampleResult("r", "railway", 10.0, status, None, 0)
        assert s.is_client_error

    @pytest.mark.parametrize("status", [401, 403])
    def test_is_client_error_falso_para_auth(self, status: int):
        s = bpa.SampleResult("r", "railway", 10.0, status, None, 0)
        assert not s.is_client_error

    def test_is_client_error_falso_para_rede(self):
        s = bpa.SampleResult("r", "railway", None, None, "network", 0)
        assert not s.is_client_error

    def test_is_client_error_falso_para_2xx(self):
        s = bpa.SampleResult("r", "railway", 10.0, 200, None, 0)
        assert not s.is_client_error
