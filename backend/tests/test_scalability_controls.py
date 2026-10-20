"""Testes unitários de controles de escalabilidade e esqueletos condicionais (P14a–P14d).

Nenhuma alteração de produção foi aplicada na família P14 (status: aguardando evidência
empírica de P12/P13). Este módulo protege os invariantes atuais de `startup.py`,
`utils.py`, `dashboard.py` e as especificações puras de isolamento de chave (`ISO-34`).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.api.routers.dashboard import _format_bucket
from app.api.routers.utils import portugal_address_from_geoapi
from startup import (
    _positive_int,
    _validate_rate_limit_workers,
    _validated_forwarded_allow_ips,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# P14d — Controles de escalabilidade e startup
# ---------------------------------------------------------------------------

def test_positive_int_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("TEST_POSITIVE_INT", raising=False)
    assert _positive_int("TEST_POSITIVE_INT", 7) == 7


def test_positive_int_reads_valid_env(monkeypatch):
    monkeypatch.setenv("TEST_POSITIVE_INT", "42")
    assert _positive_int("TEST_POSITIVE_INT", 7) == 42


@pytest.mark.parametrize("raw", ["0", "-1", "-42"])
def test_positive_int_rejects_non_positive(monkeypatch, raw):
    monkeypatch.setenv("TEST_POSITIVE_INT", raw)
    with pytest.raises(RuntimeError):
        _positive_int("TEST_POSITIVE_INT", 7)


@pytest.mark.parametrize("raw", ["abc", "1.5", "", "  "])
def test_positive_int_rejects_non_integer(monkeypatch, raw):
    monkeypatch.setenv("TEST_POSITIVE_INT", raw)
    with pytest.raises(RuntimeError):
        _positive_int("TEST_POSITIVE_INT", 7)


def test_rate_limit_workers_single_worker_memory_ok():
    _validate_rate_limit_workers(1, "memory://")


def test_rate_limit_workers_multi_worker_memory_rejected():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_STORAGE_URI compartilhado"):
        _validate_rate_limit_workers(2, "memory://")


def test_rate_limit_workers_multi_worker_redis_ok():
    _validate_rate_limit_workers(2, "redis://localhost:6379/0")


def test_forwarded_allow_ips_accepts_valid_list():
    raw = "127.0.0.1,100.64.0.0/10"
    assert _validated_forwarded_allow_ips(raw) == raw


@pytest.mark.parametrize(
    "raw",
    ["*", "0.0.0.0/0", "::/0", "", "   ", "not-an-ip", "127.0.0.1,not-an-ip"],
)
def test_forwarded_allow_ips_rejects_invalid(raw):
    with pytest.raises(RuntimeError):
        _validated_forwarded_allow_ips(raw)


# ---------------------------------------------------------------------------
# P14a — Contrato atual de normalização de endereço PT e chave condicional
# ---------------------------------------------------------------------------

def test_portugal_address_from_geoapi_uses_partes():
    data = {
        "partes": [
            {"Artéria": "Rua Augusta"},
        ],
        "Localidade": "Lisboa",
        "Distrito": "Lisboa",
    }
    result = portugal_address_from_geoapi(data)
    assert result == {
        "logradouro": "Rua Augusta",
        "bairro": "",
        "localidade": "Lisboa",
        "uf": "--",
        "regiao": "Lisboa",
    }


def test_portugal_address_from_geoapi_falls_back_to_ruas_and_concelho():
    data = {
        "ruas": ["Avenida da Liberdade"],
        "Concelho": "Porto",
        "Distrito": "Porto",
    }
    result = portugal_address_from_geoapi(data)
    assert result == {
        "logradouro": "Avenida da Liberdade",
        "bairro": "",
        "localidade": "Porto",
        "uf": "--",
        "regiao": "Porto",
    }


def build_postal_cache_key(country: str, market: str, raw_code: str) -> str:
    """Especificação pura da chave de cache condicional de P14a (`ISO-34`)."""
    country_norm = (country or "").strip().upper()
    market_norm = (market or "").strip().upper()
    digits = "".join(c for c in (raw_code or "") if c.isdigit())
    return f"postal:v1:{country_norm}:{market_norm}:{digits}"


def test_postal_cache_key_br_and_eu_never_collide():
    br = build_postal_cache_key("BR", "BR", "01001-000")
    pt = build_postal_cache_key("PT", "EU", "1000-001")
    same_digits_cross_market = build_postal_cache_key("BR", "EU", "01001000")
    assert br != pt
    assert br != same_digits_cross_market
    assert br == build_postal_cache_key("br", "br", "01001000")


# ---------------------------------------------------------------------------
# P14c — Contrato atual de granularidade do dashboard e chave condicional
# ---------------------------------------------------------------------------

def test_format_bucket_day_week_month():
    sample_dt = datetime(2026, 3, 15, 10, 30)
    assert _format_bucket(sample_dt, "day") == "2026-03-15"
    assert _format_bucket(sample_dt, "week") == "2026-03-15"
    assert _format_bucket(sample_dt, "month") == "2026-03"


def build_dashboard_cache_key(
    market_code: str,
    start_date: str,
    end_date: str,
    rep_id: str | None,
    region: str | None,
    ranking_limit: int,
) -> str:
    """Especificação pura da chave de cache condicional de P14c (`ISO-34`)."""
    market_norm = (market_code or "").strip().upper()
    start_norm = (start_date or "").strip()
    end_norm = (end_date or "").strip()
    rep_norm = (rep_id or "*").strip()
    region_norm = (region or "*").strip().upper()
    return (
        f"dash:v1:{market_norm}:{start_norm}:{end_norm}:"
        f"{rep_norm}:{region_norm}:{int(ranking_limit)}"
    )


def test_dashboard_cache_key_isolates_markets_and_filters():
    br = build_dashboard_cache_key("BR", "2026-01-01", "2026-01-30", None, None, 100)
    eu = build_dashboard_cache_key("EU", "2026-01-01", "2026-01-30", None, None, 100)
    assert br != eu
    assert br != build_dashboard_cache_key("BR", "2026-01-01", "2026-01-30", "rep-1", None, 100)
    assert br != build_dashboard_cache_key("BR", "2026-01-01", "2026-01-30", None, "SUL", 100)
    assert br != build_dashboard_cache_key("BR", "2026-01-01", "2026-01-30", None, None, 50)
