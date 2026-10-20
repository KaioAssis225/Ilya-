"""Testes unitários para `ops/synthetic_monitor.py` (Bloco P15)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import synthetic_monitor as sm


class _FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.headers = headers or {}

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _json_resp(payload, status: int = 200, headers: dict | None = None) -> _FakeResponse:
    return _FakeResponse(
        status=status,
        body=json.dumps(payload).encode("utf-8"),
        headers=headers or {},
    )


class TestSyntheticMonitor(unittest.TestCase):
    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        for k in (
            "SYNTHETIC_COMMERCIAL_ENABLED",
            "ILYA_CANARY_BR_USERNAME",
            "ILYA_CANARY_BR_PASSWORD",
            "ILYA_CANARY_EU_USERNAME",
            "ILYA_CANARY_EU_PASSWORD",
        ):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env_patch.stop()

    def test_commercial_probe_inert_by_default(self):
        with mock.patch.object(sm, "_open_no_redirect") as m:
            results = sm.run_commercial_canary_probes("https://staging.example.com")
            self.assertEqual(m.call_count, 0)

        by_market = {r.market: r for r in results}
        self.assertEqual(by_market["BR"].status, "skipped_inactive")
        self.assertEqual(by_market["EU"].status, "skipped_inactive")

        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "false"
        os.environ["ILYA_CANARY_BR_USERNAME"] = "u"
        os.environ["ILYA_CANARY_BR_PASSWORD"] = "p"
        os.environ["ILYA_CANARY_EU_USERNAME"] = "u"
        os.environ["ILYA_CANARY_EU_PASSWORD"] = "p"
        with mock.patch.object(sm, "_open_no_redirect") as m:
            results = sm.run_commercial_canary_probes("https://staging.example.com")
            self.assertEqual(m.call_count, 0)
        for r in results:
            self.assertEqual(r.status, "skipped_inactive")

        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        os.environ.pop("ILYA_CANARY_BR_USERNAME", None)
        os.environ.pop("ILYA_CANARY_EU_USERNAME", None)
        with mock.patch.object(sm, "_open_no_redirect") as m:
            results = sm.run_commercial_canary_probes("https://staging.example.com")
            self.assertEqual(m.call_count, 0)
        for r in results:
            self.assertFalse(r.ok)
            self.assertEqual(r.status, "config_error")

    def test_enabled_probe_with_missing_market_credentials_is_config_error(self):
        complete = {
            "SYNTHETIC_COMMERCIAL_ENABLED": "true",
            "ILYA_CANARY_BR_USERNAME": "br-user",
            "ILYA_CANARY_BR_PASSWORD": "br-pass-secret",
            "ILYA_CANARY_EU_USERNAME": "eu-user",
            "ILYA_CANARY_EU_PASSWORD": "eu-pass-secret",
        }
        for market, other in (("BR", "EU"), ("EU", "BR")):
            for missing_var in (
                f"ILYA_CANARY_{market}_USERNAME",
                f"ILYA_CANARY_{market}_PASSWORD",
            ):
                with self.subTest(missing=missing_var):
                    os.environ.update(complete)
                    os.environ[missing_var] = "  "
                    ok_other = sm.CheckResult(
                        name=f"commercial/{other.lower()}", ok=True, market=other
                    )
                    with mock.patch.object(
                        sm, "run_commercial_canary_probe", return_value=ok_other
                    ) as probe, mock.patch.object(sm, "_open_no_redirect") as net:
                        results = sm.run_commercial_canary_probes(
                            "https://staging.example.com"
                        )
                    self.assertEqual(net.call_count, 0)
                    self.assertEqual(probe.call_count, 1)
                    self.assertEqual(probe.call_args.args[1], other)

                    by_market = {r.market: r for r in results}
                    self.assertFalse(by_market[market].ok)
                    self.assertEqual(by_market[market].status, "config_error")
                    self.assertIn(missing_var, by_market[market].detail)
                    dumped = json.dumps([r.to_dict() for r in results])
                    self.assertNotIn("br-pass-secret", dumped)
                    self.assertNotIn("eu-pass-secret", dumped)

    def test_single_probe_enabled_without_credentials_is_config_error(self):
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        with mock.patch.object(sm, "_request") as req:
            res = sm.run_commercial_canary_probe(
                "https://staging.example.com", "EU", "eu-user", ""
            )
        self.assertEqual(req.call_count, 0)
        self.assertFalse(res.ok)
        self.assertEqual(res.status, "config_error")

    def test_main_exits_nonzero_when_enabled_without_credentials(self):
        healthy = [sm.CheckResult(name="/health/live", ok=True, status_code=200)]
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        os.environ["ILYA_CANARY_BR_USERNAME"] = "br-user"
        os.environ["ILYA_CANARY_BR_PASSWORD"] = "br-pass-secret"
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "result.json")
            with mock.patch.object(
                sm, "check_health", return_value=healthy
            ), mock.patch.object(
                sm,
                "run_commercial_canary_probe",
                return_value=sm.CheckResult(name="commercial/br", ok=True, market="BR"),
            ):
                code = sm.main(["--mode", "check", "--output", out])
            with open(out, encoding="utf-8") as fh:
                raw = fh.read()
        payload = json.loads(raw)
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual([f["market"] for f in payload["failures"]], ["EU"])
        self.assertEqual(payload["failures"][0]["status"], "config_error")
        self.assertIn("ILYA_CANARY_EU_USERNAME", payload["alert_body"])
        self.assertNotIn("br-pass-secret", raw)

    def test_main_ok_when_commercial_deliberately_disabled(self):
        healthy = [sm.CheckResult(name="/health/live", ok=True, status_code=200)]
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "false"
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "result.json")
            with mock.patch.object(sm, "check_health", return_value=healthy):
                code = sm.main(["--mode", "check", "--output", out])
            with open(out, encoding="utf-8") as fh:
                payload = json.load(fh)
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        statuses = {r["market"]: r["status"] for r in payload["results"] if r["market"]}
        self.assertEqual(statuses, {"BR": "skipped_inactive", "EU": "skipped_inactive"})

    def test_commercial_url_must_be_https_pure_origin(self):
        bad_urls = [
            "http://staging.example.com",
            "https://user:pw-secret@staging.example.com",
            "https://:pw-secret@staging.example.com",
            "https://pw-secret@staging.example.com",
            "https://staging.example.com/api",
            "https://staging.example.com/api/v1/",
            "https://staging.example.com?next=pw-secret",
            "https://staging.example.com#pw-secret",
            "https://staging.example.com;pw-secret",
            "https://staging.example.com:pw-secret",
            "https://staging.example.com:",
            "https://staging.example.com\\@evil.example.com",
            "https://staging .example.com",
            "https://staging.example.com\n",
            "https://staging_example.com",
            "https:///api",
            "ftp://staging.example.com",
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as ctx:
                    sm._validate_commercial_base_url(url)
                self.assertNotIn("pw-secret", str(ctx.exception))

        self.assertEqual(
            sm._validate_commercial_base_url("https://staging.example.com/"),
            "https://staging.example.com",
        )
        self.assertEqual(
            sm._validate_commercial_base_url("https://Staging.Example.com:8443"),
            "https://Staging.Example.com:8443",
        )

    def test_commercial_probe_rejects_insecure_url_before_request(self):
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        for url in (
            "http://staging.example.com",
            "https://staging.example.com/prefix",
            "https://staging.example.com?x=1",
        ):
            with self.subTest(url=url):
                with mock.patch.object(sm, "_request") as req:
                    with self.assertRaises(ValueError) as ctx:
                        sm.run_commercial_canary_probe(
                            url, "BR", "br-user", "br-pass-secret"
                        )
                self.assertEqual(req.call_count, 0)
                self.assertNotIn("br-pass-secret", str(ctx.exception))

    def test_commercial_probes_insecure_url_yields_config_error_without_network(self):
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        os.environ["ILYA_CANARY_BR_USERNAME"] = "br-user"
        os.environ["ILYA_CANARY_BR_PASSWORD"] = "br-pass-secret"
        os.environ["ILYA_CANARY_EU_USERNAME"] = "eu-user"
        os.environ["ILYA_CANARY_EU_PASSWORD"] = "eu-pass-secret"
        with mock.patch.object(sm, "_request") as req:
            results = sm.run_commercial_canary_probes("http://staging.example.com")
        self.assertEqual(req.call_count, 0)
        self.assertEqual([r.status for r in results], ["config_error", "config_error"])
        self.assertTrue(all(not r.ok for r in results))
        dumped = json.dumps([r.to_dict() for r in results])
        self.assertNotIn("br-pass-secret", dumped)
        self.assertNotIn("eu-pass-secret", dumped)

    def test_local_http_health_still_allowed_without_credentials(self):
        with mock.patch.object(
            sm, "_open_no_redirect", return_value=_json_resp({"status": "ok"})
        ) as net:
            health = sm.check_health("http://localhost:8000")
            commercial = sm.run_commercial_canary_probes("http://localhost:8000")
        self.assertEqual(net.call_count, 2)
        self.assertTrue(all(r.ok for r in health))
        self.assertEqual(
            [r.status for r in commercial], ["skipped_inactive", "skipped_inactive"]
        )

    def test_base_url_errors_do_not_echo_secrets(self):
        with self.assertRaises(ValueError) as ctx:
            sm.check_health("http://user:pw-secret@localhost:8000")
        self.assertNotIn("pw-secret", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            sm.check_health("gopher://pw-secret")
        self.assertNotIn("pw-secret", str(ctx.exception))

    def test_rejects_vercel_health_url(self):
        with self.assertRaises(ValueError):
            sm.check_health("https://ilya-rust.vercel.app")
        with self.assertRaises(ValueError):
            sm.check_health("https://ilya-rust.vercel.app/health")

    def test_commercial_probe_authenticated_readonly_br_and_eu(self):
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        os.environ["ILYA_CANARY_BR_USERNAME"] = "br-user"
        os.environ["ILYA_CANARY_BR_PASSWORD"] = "br-pass"
        os.environ["ILYA_CANARY_EU_USERNAME"] = "eu-user"
        os.environ["ILYA_CANARY_EU_PASSWORD"] = "eu-pass"

        calls = []
        current_market = {"value": "BR"}

        def fake_open(req, timeout=15.0):
            url = req.full_url
            method = req.get_method()
            headers = dict(req.header_items())
            calls.append({"method": method, "url": url, "headers": headers})
            if url.endswith("/api/v1/auth/login"):
                payload = json.loads(req.data.decode("utf-8"))
                current_market["value"] = "BR" if "br-" in payload["identifier"] else "EU"
                return _json_resp(
                    {"access_token": f"tok-{current_market['value']}"},
                    headers={"X-Request-ID": f"req-login-{current_market['value']}"},
                )
            if url.endswith("/api/v1/auth/me"):
                mkt = current_market["value"]
                return _json_resp(
                    {
                        "role": "benchmark_readonly",
                        "active_market": mkt,
                        "allowed_markets": [mkt],
                        "can_approve_tax": False,
                    },
                    headers={"X-Request-ID": f"req-me-{mkt}"},
                )
            if "/api/v1/products" in url:
                return _json_resp([], status=200, headers={"X-Request-ID": "req-prod-1"})
            if "/api/v1/orders" in url:
                return _json_resp([], status=200, headers={"X-Request-ID": "req-ord-1"})
            raise AssertionError(f"unexpected URL: {url}")

        with mock.patch.object(sm, "_open_no_redirect", side_effect=fake_open):
            results = sm.run_commercial_canary_probes("https://staging.example.com")

        by_market = {r.market: r for r in results}
        self.assertEqual(by_market["BR"].status, "ok")
        self.assertEqual(by_market["EU"].status, "ok")
        self.assertEqual(by_market["BR"].http_status, 200)
        self.assertEqual(by_market["EU"].http_status, 200)

        post_login_calls = [c for c in calls if not c["url"].endswith("/api/v1/auth/login")]
        self.assertEqual(len(post_login_calls), 6)  # me + products + orders for BR and EU
        for c in post_login_calls:
            self.assertEqual(c["method"], "GET")

    def test_commercial_probe_fails_on_scope_mismatch(self):
        os.environ["SYNTHETIC_COMMERCIAL_ENABLED"] = "true"
        os.environ["ILYA_CANARY_BR_USERNAME"] = "br-user"
        os.environ["ILYA_CANARY_BR_PASSWORD"] = "br-pass"

        scenarios = [
            {"role": "admin", "active_market": "BR", "allowed_markets": ["BR"], "can_approve_tax": False},
            {"role": "benchmark_readonly", "active_market": "EU", "allowed_markets": ["EU"], "can_approve_tax": False},
            {"role": "benchmark_readonly", "active_market": "BR", "allowed_markets": ["BR"], "can_approve_tax": True},
        ]

        for scenario in scenarios:
            calls = []

            def fake_open(req, timeout=15.0, _sc=scenario):
                url = req.full_url
                calls.append(url)
                if url.endswith("/api/v1/auth/login"):
                    return _json_resp({"access_token": "tok-123"})
                if url.endswith("/api/v1/auth/me"):
                    return _json_resp(_sc)
                raise AssertionError(f"should not call {url} when scope fails")

            with mock.patch.object(sm, "_open_no_redirect", side_effect=fake_open):
                res = sm.run_commercial_canary_probe(
                    "https://staging.example.com", "BR", "br-user", "br-pass"
                )

            self.assertFalse(res.ok)
            self.assertEqual(res.status, "failed")
            self.assertIn("scope error", res.detail)
            for called_url in calls:
                self.assertNotIn("/api/v1/products", called_url)
                self.assertNotIn("/api/v1/orders", called_url)

    def test_alert_body_contains_metadata_and_redacts_secrets_and_pii(self):
        error_msg = (
            "Authorization: Bearer secret-jwt "
            "password=supersecret "
            "Cookie: sid=123 "
            "contact user@example.com "
            "cpf 123.456.789-00"
        )
        failure = sm.CheckResult(
            name="/api/v1/products",
            ok=False,
            status_code=503,
            duration_ms=1234,
            request_id="req-abc-123",
            detail=error_msg,
            status="failed",
        )
        body = sm.format_alert_body(
            failures=[failure],
            run_url="https://github.com/org/repo/actions/runs/42",
            commit_sha="abc123def",
            app_version="1.2.3",
            now_utc=datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        self.assertIn(sm.FAILURE_MARKER, body)
        self.assertIn("abc123def", body)
        self.assertIn("1.2.3", body)
        self.assertIn("https://github.com/org/repo/actions/runs/42", body)
        self.assertIn("/api/v1/products", body)
        self.assertIn("503", body)
        self.assertIn("1234", body)
        self.assertIn("req-abc-123", body)
        self.assertIn("2026-10-20T12:00:00Z", body)
        self.assertIn("2026-10-20T09:00:00-03:00", body)

        self.assertNotIn("secret-jwt", body)
        self.assertNotIn("supersecret", body)
        self.assertNotIn("sid=123", body)
        self.assertNotIn("user@example.com", body)
        self.assertNotIn("123.456.789-00", body)
        self.assertIn("[REDACTED]", body)
        self.assertIn("[REDACTED_EMAIL]", body)
        self.assertIn("[REDACTED_CPF]", body)

    def test_cookie_redaction_covers_all_pairs_and_keeps_following_text(self):
        out = sm._sanitize(
            "Cookie: sid=abc123; csrftoken=xyz789;theme=dark contact "
            "maria@example.com cpf 123.456.789-00 status 503"
        )
        for secret in ("abc123", "xyz789", "dark", "maria@example.com", "123.456.789-00"):
            self.assertNotIn(secret, out)
        self.assertIn("Cookie: [REDACTED] contact [REDACTED_EMAIL]", out)
        self.assertIn("cpf [REDACTED_CPF] status 503", out)

    def test_set_cookie_attributes_and_folded_cookies_redacted(self):
        out = sm._sanitize(
            "Set-Cookie: session=s3cr3t; Path=/; Expires=Wed, 21 Oct 2026 07:28:00 GMT, "
            "refresh=r3fr3sh; HttpOnly; Secure titular 12345678900 joao@example.org"
        )
        for secret in ("s3cr3t", "r3fr3sh", "12345678900", "joao@example.org"):
            self.assertNotIn(secret, out)
        self.assertIn("Set-Cookie: [REDACTED] titular [REDACTED_CPF] [REDACTED_EMAIL]", out)

    def test_cookie_pairs_separated_by_space_do_not_leak(self):
        out = sm._sanitize("cookie=sid=abc other=def\tlast=ghi next step")
        for secret in ("abc", "def", "ghi"):
            self.assertNotIn(secret, out)
        self.assertTrue(out.endswith("[REDACTED] next step"))

    def test_cookie_quoted_value_with_spaces_is_redacted(self):
        out = sm._sanitize('Cookie: session="abc def" contact user@example.com')
        self.assertNotIn("abc def", out)
        self.assertIn("Cookie: [REDACTED] contact [REDACTED_EMAIL]", out)

    def test_unclosed_cookie_quote_redacts_rest_of_line(self):
        out = sm._sanitize('Cookie: session="abc def contact user@example.com')
        self.assertNotIn("abc def", out)
        self.assertNotIn("user@example.com", out)

    def test_recovery_requires_two_consecutive_healthy_runs(self):
        r1 = sm.evaluate_recovery_transition(existing_comments=[], recovery_timestamp_utc="2026-10-20T12:00:00Z")
        self.assertFalse(r1["should_close"])
        self.assertEqual(r1["streak"], 1)
        self.assertEqual(r1["action"], "first_recovery")
        self.assertIn(sm.RECOVERY_MARKER_1, r1["comment_body"])

        r1b = sm.evaluate_recovery_transition(
            existing_comments=[sm.FAILURE_MARKER],
            recovery_timestamp_utc="2026-10-20T12:15:00Z",
        )
        self.assertFalse(r1b["should_close"])
        self.assertEqual(r1b["streak"], 1)
        self.assertEqual(r1b["action"], "first_recovery")

        r2 = sm.evaluate_recovery_transition(
            existing_comments=[sm.FAILURE_MARKER, sm.RECOVERY_MARKER_1],
            recovery_timestamp_utc="2026-10-20T12:30:00Z",
        )
        self.assertTrue(r2["should_close"])
        self.assertEqual(r2["streak"], 2)
        self.assertEqual(r2["action"], "second_recovery")
        self.assertIn(sm.RECOVERY_MARKER_2, r2["comment_body"])

        r3 = sm.evaluate_recovery_transition(
            existing_comments=[sm.RECOVERY_MARKER_1, sm.FAILURE_MARKER],
            recovery_timestamp_utc="2026-10-20T12:45:00Z",
        )
        self.assertFalse(r3["should_close"])
        self.assertEqual(r3["streak"], 1)
        self.assertEqual(r3["action"], "first_recovery")


if __name__ == "__main__":
    unittest.main()
