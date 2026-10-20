"""Testes unitários para `ops/synthetic_monitor.py` (Bloco P15)."""

from __future__ import annotations

import json
import os
import sys
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
            self.assertEqual(r.status, "skipped_inactive")

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
