"""Monitor sintético de produção para a API Ilya (Bloco P15).

Executa:
  * Verificações diretas de `/health/live` e `/health/ready` na Railway (recusando
    qualquer URL da Vercel como sinal de saúde do backend).
  * Sondas comerciais canário somente leitura para os mercados BR e EU, inertes
    por padrão (`SYNTHETIC_COMMERCIAL_ENABLED=true` + credenciais por mercado).
    Habilitadas, exigem origem HTTPS sem userinfo/caminho/query e credenciais
    completas; caso contrário viram `config_error` (saída 2), nunca `skipped_inactive`.
  * Formatação de corpo de alerta sanitizado (sem tokens, cookies, senhas ou PII),
    com horários em UTC e America/Sao_Paulo (-03:00), X-Request-ID e versão.
  * Máquina de estados determinística de recuperação em duas execuções saudáveis
    consecutivas antes de fechar a issue de alerta.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DEFAULT_BASE_URL = "https://ilya-production-7857.up.railway.app"
FORBIDDEN_HEALTH_SIGNAL_HOST = "ilya-rust.vercel.app"
HEALTH_ENDPOINTS = ("live", "ready")
COMMERCIAL_PRODUCTS_PATH = "/api/v1/products?limit=5&include_total=false"
COMMERCIAL_ORDERS_PATH = "/api/v1/orders?limit=5"
RECOVERY_MARKER_1 = "<!-- synthetic-recovery-streak:1 -->"
RECOVERY_MARKER_2 = "<!-- synthetic-recovery-streak:2 -->"
FAILURE_MARKER = "<!-- synthetic-monitor-failure -->"
SAO_PAULO_TZ = timezone(timedelta(hours=-3))

DEFAULT_TIMEOUT_SECONDS = 15.0
USER_AGENT = "ilya-synthetic-monitor/1.0"


@dataclass
class CheckResult:
    name: str
    ok: bool
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    request_id: Optional[str] = None
    detail: str = ""
    version: Optional[str] = None
    status: str = "ok"
    market: Optional[str] = None

    @property
    def http_status(self) -> Optional[int]:
        return self.status_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "status_code": self.status_code,
            "http_status": self.status_code,
            "duration_ms": self.duration_ms,
            "request_id": self.request_id,
            "detail": self.detail,
            "version": self.version,
            "status": self.status,
            "market": self.market,
        }

    def __getitem__(self, item: str) -> Any:
        return self.to_dict()[item]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_no_redirect(
    req: urllib.request.Request, timeout: float = DEFAULT_TIMEOUT_SECONDS
):
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(req, timeout=timeout)


def _validate_base_url(base_url: str) -> str:
    if not base_url:
        raise ValueError("base_url is required")
    parsed = urllib.parse.urlparse(base_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == FORBIDDEN_HEALTH_SIGNAL_HOST or host.endswith(
        "." + FORBIDDEN_HEALTH_SIGNAL_HOST
    ):
        raise ValueError(
            f"Recusado usar {FORBIDDEN_HEALTH_SIGNAL_HOST} como sinal de saúde do backend."
        )
    if parsed.scheme not in ("https", "http") or not host:
        raise ValueError("base_url inválida: use http(s) com host")
    if "@" in parsed.netloc:
        raise ValueError("base_url não pode conter credenciais (userinfo)")
    return base_url.rstrip("/")


_HOSTNAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$"
)


def _validate_commercial_base_url(base_url: str) -> str:
    """Valida a origem credenciada antes de qualquer envio de senha.

    Exige HTTPS e origem pura (host e porta opcional), sem userinfo, caminho,
    query ou fragmento. As mensagens de erro nunca repetem a URL recebida.
    """
    if any(
        ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F or ch == "\\"
        for ch in base_url or ""
    ):
        raise ValueError("URL comercial contém caracteres inválidos")
    base_url = _validate_base_url(base_url)
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https":
        raise ValueError("URL comercial deve usar HTTPS")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(
            "URL comercial deve ser apenas a origem, sem caminho, query ou fragmento"
        )
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("URL comercial com porta inválida") from None
    expected_netloc = host if port is None else f"{host}:{port}"
    if not _HOSTNAME_RE.match(host) or parsed.netloc.lower() != expected_netloc:
        raise ValueError("URL comercial com host inválido")
    return f"https://{parsed.netloc}"


def _request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    started = time.monotonic()
    try:
        with _open_no_redirect(req, timeout=timeout) as resp:
            raw = resp.read()
            duration_ms = int((time.monotonic() - started) * 1000)
            status_code = getattr(resp, "status", None) or resp.getcode()
            return {
                "ok": True,
                "status_code": status_code,
                "headers": dict(resp.headers.items()),
                "body": raw,
                "duration_ms": duration_ms,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        return {
            "ok": False,
            "status_code": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "body": raw,
            "duration_ms": duration_ms,
            "error": f"HTTPError: {exc.code}",
        }
    except urllib.error.URLError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "headers": {},
            "body": b"",
            "error": f"URLError: {exc.reason}",
            "duration_ms": duration_ms,
        }
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "headers": {},
            "body": b"",
            "error": f"{type(exc).__name__}: {exc}",
            "duration_ms": duration_ms,
        }


def _header(headers: Dict[str, str], name: str) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _parse_json(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None


def check_health(base_url: str = DEFAULT_BASE_URL) -> List[CheckResult]:
    base_url = _validate_base_url(base_url)
    results: List[CheckResult] = []
    for endpoint in HEALTH_ENDPOINTS:
        url = f"{base_url}/health/{endpoint}"
        resp = _request("GET", url)
        request_id = _header(resp.get("headers") or {}, "X-Request-ID")
        parsed = _parse_json(resp.get("body") or b"")
        version = None
        if isinstance(parsed, dict):
            version = parsed.get("version") or parsed.get("app_version")
        ok = bool(resp.get("ok")) and resp.get("status_code") == 200
        detail = ""
        if not ok:
            detail = resp.get("error") or f"unexpected status {resp.get('status_code')}"
        results.append(
            CheckResult(
                name=f"/health/{endpoint}",
                ok=ok,
                status_code=resp.get("status_code"),
                duration_ms=resp.get("duration_ms"),
                request_id=request_id,
                detail=detail,
                version=version,
                status="ok" if ok else "failed",
            )
        )
    return results


def _commercial_enabled() -> bool:
    return os.environ.get("SYNTHETIC_COMMERCIAL_ENABLED", "").strip().lower() == "true"


def _market_credentials(market: str) -> Optional[Dict[str, str]]:
    market = market.upper()
    username = os.environ.get(f"ILYA_CANARY_{market}_USERNAME", "").strip()
    password = os.environ.get(f"ILYA_CANARY_{market}_PASSWORD", "").strip()
    if not username or not password:
        return None
    return {"identifier": username, "password": password}


def _missing_credential_vars(market: str) -> List[str]:
    market = market.upper()
    names = (f"ILYA_CANARY_{market}_USERNAME", f"ILYA_CANARY_{market}_PASSWORD")
    return [name for name in names if not os.environ.get(name, "").strip()]


def _skipped(market: str, reason: str) -> CheckResult:
    market = market.upper()
    return CheckResult(
        name=f"commercial/{market.lower()}",
        ok=True,
        status="skipped_inactive",
        detail=reason,
        market=market,
    )


def _config_error(market: str, reason: str) -> CheckResult:
    market = market.upper()
    return CheckResult(
        name=f"commercial/{market.lower()}",
        ok=False,
        status="config_error",
        detail=reason,
        market=market,
    )


def run_commercial_canary_probe(
    base_url: str,
    market: str,
    identifier: str,
    password: str,
) -> CheckResult:
    base_url = _validate_base_url(base_url)
    market = market.upper()
    name = f"commercial/{market.lower()}"

    if not _commercial_enabled():
        return _skipped(market, "SYNTHETIC_COMMERCIAL_ENABLED is not true")
    if not identifier or not password:
        return _config_error(
            market,
            f"SYNTHETIC_COMMERCIAL_ENABLED=true sem credenciais completas para {market}",
        )
    # Levanta ValueError antes de qualquer _request se a origem não for HTTPS íntegra.
    base_url = _validate_commercial_base_url(base_url)

    token: Optional[str] = None
    try:
        login_body = json.dumps(
            {"identifier": identifier, "password": password}
        ).encode("utf-8")
        login_resp = _request(
            "POST",
            f"{base_url}/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=login_body,
        )
        if not login_resp.get("ok") or login_resp.get("status_code") != 200:
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=login_resp.get("status_code"),
                duration_ms=login_resp.get("duration_ms"),
                request_id=_header(login_resp.get("headers") or {}, "X-Request-ID"),
                detail=f"login failed: {login_resp.get('error') or 'non-200'}",
                market=market,
            )
        login_json = _parse_json(login_resp.get("body") or b"")
        if not isinstance(login_json, dict):
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=login_resp.get("status_code"),
                duration_ms=login_resp.get("duration_ms"),
                detail="login response not JSON object",
                market=market,
            )
        token = login_json.get("access_token")
        if not token or not isinstance(token, str):
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=login_resp.get("status_code"),
                duration_ms=login_resp.get("duration_ms"),
                detail="login response missing access_token",
                market=market,
            )

        auth_headers = {"Authorization": f"Bearer {token}"}

        me_resp = _request("GET", f"{base_url}/api/v1/auth/me", headers=auth_headers)
        me_request_id = _header(me_resp.get("headers") or {}, "X-Request-ID")
        if not me_resp.get("ok") or me_resp.get("status_code") != 200:
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=me_resp.get("status_code"),
                duration_ms=me_resp.get("duration_ms"),
                request_id=me_request_id,
                detail=f"auth/me failed: {me_resp.get('error') or 'non-200'}",
                market=market,
            )
        me_json = _parse_json(me_resp.get("body") or b"")
        if not isinstance(me_json, dict):
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=me_resp.get("status_code"),
                duration_ms=me_resp.get("duration_ms"),
                request_id=me_request_id,
                detail="auth/me response not JSON object",
                market=market,
            )

        scope_errors: List[str] = []
        if me_json.get("role") != "benchmark_readonly":
            scope_errors.append("role mismatch")
        if me_json.get("active_market") != market:
            scope_errors.append("active_market mismatch")
        allowed = me_json.get("allowed_markets")
        if allowed != [market]:
            scope_errors.append("allowed_markets mismatch")
        if "can_approve_tax" in me_json and me_json.get("can_approve_tax") is not False:
            scope_errors.append("can_approve_tax must be false")
        if scope_errors:
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=me_resp.get("status_code"),
                duration_ms=me_resp.get("duration_ms"),
                request_id=me_request_id,
                detail=f"scope error: {', '.join(scope_errors)}",
                market=market,
            )

        products_resp = _request(
            "GET", f"{base_url}{COMMERCIAL_PRODUCTS_PATH}", headers=auth_headers
        )
        products_request_id = _header(products_resp.get("headers") or {}, "X-Request-ID")
        products_json = _parse_json(products_resp.get("body") or b"")
        products_ok = (
            products_resp.get("ok")
            and products_resp.get("status_code") == 200
            and isinstance(products_json, (list, dict))
        )
        if not products_ok:
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=products_resp.get("status_code"),
                duration_ms=products_resp.get("duration_ms"),
                request_id=products_request_id,
                detail=f"products probe failed: {products_resp.get('error') or 'invalid response'}",
                market=market,
            )

        orders_resp = _request(
            "GET", f"{base_url}{COMMERCIAL_ORDERS_PATH}", headers=auth_headers
        )
        orders_request_id = _header(orders_resp.get("headers") or {}, "X-Request-ID")
        orders_json = _parse_json(orders_resp.get("body") or b"")
        orders_ok = (
            orders_resp.get("ok")
            and orders_resp.get("status_code") == 200
            and isinstance(orders_json, (list, dict))
        )
        if not orders_ok:
            return CheckResult(
                name=name,
                ok=False,
                status="failed",
                status_code=orders_resp.get("status_code"),
                duration_ms=orders_resp.get("duration_ms"),
                request_id=orders_request_id,
                detail=f"orders probe failed: {orders_resp.get('error') or 'invalid response'}",
                market=market,
            )

        return CheckResult(
            name=name,
            ok=True,
            status="ok",
            status_code=orders_resp.get("status_code"),
            duration_ms=products_resp.get("duration_ms"),
            request_id=products_request_id or orders_request_id,
            detail="commercial canary ok",
            market=market,
        )
    finally:
        token = None  # noqa: F841 - descartado explicitamente, nunca persistido


def run_commercial_canary_probes(base_url: str = DEFAULT_BASE_URL) -> List[CheckResult]:
    base_url = _validate_base_url(base_url)
    markets = ("BR", "EU")
    if not _commercial_enabled():
        return [
            _skipped(market, "SYNTHETIC_COMMERCIAL_ENABLED is not true")
            for market in markets
        ]
    try:
        base_url = _validate_commercial_base_url(base_url)
    except ValueError as exc:
        return [_config_error(market, str(exc)) for market in markets]

    results: List[CheckResult] = []
    for market in markets:
        creds = _market_credentials(market)
        if creds is None:
            missing = ", ".join(_missing_credential_vars(market)) or f"credenciais {market}"
            results.append(
                _config_error(market, f"SYNTHETIC_COMMERCIAL_ENABLED=true sem {missing}")
            )
            continue
        results.append(
            run_commercial_canary_probe(
                base_url,
                market,
                creds["identifier"],
                creds["password"],
            )
        )
    return results


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]+")
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)")
# Um item de cookie: `Expires=<data HTTP>` (contém vírgula e espaços) ou um token
# sem espaço/separador. O valor redigido cobre itens unidos por `;`/`,` e pares
# `nome=valor` separados só por espaço, parando no primeiro texto livre seguinte
# para que e-mail/CPF na mesma linha continuem com sua própria sanitização.
_COOKIE_PAIR = r'(?:[^\s;,=]+="(?:\\.|[^"\\\r\n])*(?:"|$)|[^\s;,=]+=[^\s;,]*)'
_COOKIE_ITEM = (
    r"(?:expires=[A-Za-z]{3},[ \t]*\d{1,2}[ \t-][A-Za-z]{3}[ \t-]\d{2,4}[ \t]+"
    r"\d{2}:\d{2}:\d{2}[ \t]*GMT|"
    + _COOKIE_PAIR
    + r"|[^\s;,]+)"
)
_COOKIE_RE = re.compile(
    r"(?i)(\b(?:set-)?cookie\s*[:=]\s*)("
    + _COOKIE_ITEM
    + r"(?:[ \t]*[;,][ \t]*"
    + _COOKIE_ITEM
    + r"|[ \t]+"
    + _COOKIE_PAIR
    + r")*)"
)
_TOKEN_KV_RE = re.compile(
    r"(?i)\b(access_token|refresh_token|token|password|senha)\b\s*[:=]\s*\"?[^\s\",;}]+\"?"
)


def _sanitize(text: str) -> str:
    if not text:
        return ""
    out = _BEARER_RE.sub("Bearer [REDACTED]", text)
    out = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", out)
    out = _COOKIE_RE.sub(r"\1[REDACTED]", out)
    out = _TOKEN_KV_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", out)
    out = _CPF_RE.sub("[REDACTED_CPF]", out)
    return out


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_sp(dt: datetime) -> str:
    return dt.astimezone(SAO_PAULO_TZ).strftime("%Y-%m-%dT%H:%M:%S-03:00")


def format_alert_body(
    failures: List[CheckResult],
    run_url: str,
    commit_sha: str,
    app_version: Optional[str],
    now_utc: Optional[datetime] = None,
    dashboard_url: str = "",
) -> str:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    utc_str = _fmt_utc(now_utc)
    sp_str = _fmt_sp(now_utc)
    dash = dashboard_url or "docs/RUNBOOK_OBSERVABILIDADE.md"

    lines: List[str] = [
        FAILURE_MARKER,
        "",
        "## Monitor sintético — falha detectada",
        "",
        f"- **Horário (UTC):** `{utc_str}`",
        f"- **Horário (America/Sao_Paulo -03:00):** `{sp_str}`",
        f"- **Commit:** `{commit_sha or 'unknown'}`",
        f"- **Versão (app_version):** `{app_version or 'unknown'}`",
        f"- **Execução:** {run_url or 'n/a'}",
        f"- **Painel / runbook:** `{dash}`",
        "",
        "| Rota lógica | Status HTTP | Duração (ms) | X-Request-ID | Detalhe sanitizado |",
        "| --- | --- | --- | --- | --- |",
    ]
    for failure in failures:
        route = _sanitize(failure.name)
        status = failure.status_code if failure.status_code is not None else "-"
        duration = failure.duration_ms if failure.duration_ms is not None else "-"
        req_id = _sanitize(failure.request_id or "-")
        detail = _sanitize(failure.detail or "-").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{route}` | {status} | {duration} | `{req_id}` | {detail} |")
    lines.append("")
    return "\n".join(lines)


def _last_relevant_comment(existing_comments: List[str]) -> Optional[str]:
    for comment in reversed(existing_comments or []):
        if not isinstance(comment, str):
            continue
        if (
            FAILURE_MARKER in comment
            or RECOVERY_MARKER_1 in comment
            or RECOVERY_MARKER_2 in comment
        ):
            return comment
    return None


def evaluate_recovery_transition(
    existing_comments: List[str], recovery_timestamp_utc: str = ""
) -> Dict[str, Any]:
    if not recovery_timestamp_utc:
        recovery_timestamp_utc = _fmt_utc(datetime.now(timezone.utc))
    last = _last_relevant_comment(existing_comments)

    if last is not None and RECOVERY_MARKER_2 in last:
        return {
            "action": "already_closed",
            "should_close": False,
            "streak": 2,
            "comment_body": "",
        }

    if last is not None and RECOVERY_MARKER_1 in last:
        body = "\n".join(
            [
                RECOVERY_MARKER_2,
                "",
                "## Monitor sintético — segunda recuperação consecutiva (2/2)",
                "",
                f"- **Horário (UTC):** `{recovery_timestamp_utc}`",
                "- **Streak:** 2/2 execuções saudáveis consecutivas.",
                "",
                "Fechando o alerta automaticamente após duas verificações saudáveis seguidas.",
                "",
            ]
        )
        return {
            "action": "second_recovery",
            "should_close": True,
            "streak": 2,
            "comment_body": body,
        }

    body = "\n".join(
        [
            RECOVERY_MARKER_1,
            "",
            "## Monitor sintético — primeira recuperação (1/2)",
            "",
            f"- **Horário (UTC):** `{recovery_timestamp_utc}`",
            "- **Streak:** 1/2 execuções saudáveis consecutivas.",
            "",
            "Primeira verificação saudável registrada. O alerta permanece aberto até a segunda recuperação consecutiva.",
            "",
        ]
    )
    return {
        "action": "first_recovery",
        "should_close": False,
        "streak": 1,
        "comment_body": body,
    }


evaluate_recovery = evaluate_recovery_transition


def _load_comments(args: argparse.Namespace) -> List[str]:
    if args.comments_json:
        try:
            data = json.loads(args.comments_json)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"invalid --comments-json: {exc}")
        if not isinstance(data, list):
            raise SystemExit("--comments-json must be a JSON array")
        return [str(item) for item in data]
    if args.comments_file:
        try:
            with open(args.comments_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"invalid --comments-file: {exc}")
        if not isinstance(data, list):
            raise SystemExit("--comments-file must contain a JSON array")
        return [str(item) for item in data]
    return []


def _write_output(path: Optional[str], payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="synthetic_monitor",
        description="Ilya authenticated synthetic monitor (Block P15)",
    )
    parser.add_argument("--mode", choices=("check", "recovery"), default="check")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--comments-json", default="")
    parser.add_argument("--comments-file", default="")
    parser.add_argument("--recovery-timestamp", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    if args.mode == "recovery":
        comments = _load_comments(args)
        ts = args.recovery_timestamp or _fmt_utc(datetime.now(timezone.utc))
        transition = evaluate_recovery_transition(comments, ts)
        _write_output(args.output, transition)
        return 0

    try:
        base_url = _validate_base_url(args.base_url)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    health_results = check_health(base_url)
    commercial_results = run_commercial_canary_probes(base_url)
    all_results = health_results + commercial_results

    failures = [
        r
        for r in all_results
        if not r.ok and r.status not in ("skipped_inactive",)
    ]

    app_version = None
    for r in health_results:
        if r.version:
            app_version = r.version
            break

    now_utc = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "base_url": base_url,
        "checked_at_utc": _fmt_utc(now_utc),
        "checked_at_sao_paulo": _fmt_sp(now_utc),
        "app_version": app_version,
        "results": [r.to_dict() for r in all_results],
        "failures": [r.to_dict() for r in failures],
        "ok": len(failures) == 0,
    }

    if failures:
        payload["alert_body"] = format_alert_body(
            failures=failures,
            run_url=args.run_url,
            commit_sha=args.commit_sha,
            app_version=app_version,
            now_utc=now_utc,
        )

    _write_output(args.output, payload)
    if any(r.status == "config_error" for r in failures):
        return 2
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
