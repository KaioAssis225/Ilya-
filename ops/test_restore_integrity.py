"""Testes unitários do verificador de integridade e dump sintético de restore (Bloco P17)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
RESTORE_PATH = os.path.join(HERE, "test_restore.py")
FIXTURES_DIR = os.path.join(HERE, "fixtures")
DUMP_PATH = os.path.join(FIXTURES_DIR, "synthetic_restore_pg16.sql")
SHA_PATH = DUMP_PATH + ".sha256"


def _load_restore_module():
    spec = importlib.util.spec_from_file_location("ops_test_restore_module", RESTORE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


restore = _load_restore_module()


class TestSyntheticDumpFixtureAndChecksum(unittest.TestCase):
    def test_synthetic_dump_fixture_and_checksum_valid(self):
        self.assertTrue(os.path.isfile(DUMP_PATH), f"missing fixture: {DUMP_PATH}")
        self.assertTrue(os.path.isfile(SHA_PATH), f"missing checksum: {SHA_PATH}")

        restore.verify_checksum(DUMP_PATH)

        with tempfile.TemporaryDirectory() as tmpdir:
            tampered = os.path.join(tmpdir, "tampered.sql")
            shutil.copyfile(DUMP_PATH, tampered)
            shutil.copyfile(SHA_PATH, tampered + ".sha256")
            with open(tampered, "r+b") as fh:
                fh.seek(0)
                first = fh.read(1)
                fh.seek(0)
                fh.write(bytes([first[0] ^ 0xFF]))
            with self.assertRaises(RuntimeError) as ctx:
                restore.verify_checksum(tampered)
            self.assertIn("SHA-256 divergente", str(ctx.exception))


class TestResolvePostgresImage(unittest.TestCase):
    def test_resolve_postgres_image_aligns_with_dump_version(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESTORE_POSTGRES_IMAGE", None)
            self.assertEqual(restore.detect_dump_pg_major(DUMP_PATH), 16)
            self.assertEqual(restore.resolve_postgres_image(DUMP_PATH), "postgres:16-alpine")

            with tempfile.TemporaryDirectory() as tmpdir:
                pg18 = os.path.join(tmpdir, "pg18.sql")
                with open(pg18, "w", encoding="utf-8") as fh:
                    fh.write("--\n-- PostgreSQL database dump\n--\n")
                    fh.write("-- Dumped from database version 18.1\n")
                    fh.write("-- Dumped by pg_dump version 18.1\n")
                self.assertEqual(restore.detect_dump_pg_major(pg18), 18)
                self.assertEqual(restore.resolve_postgres_image(pg18), "postgres:18-alpine")

            self.assertEqual(
                restore.resolve_postgres_image(DUMP_PATH, explicit_image="postgres:16.4-alpine"),
                "postgres:16.4-alpine",
            )


def _make_query_scalar(overrides=None, missing_tables=None, row_counts=None, fk_values=None):
    overrides = overrides or {}
    missing_tables = set(missing_tables or ())
    row_counts = dict(row_counts or {})
    fk_values = dict(fk_values or {})

    essential_tables = list(restore.ESSENTIAL_TABLES)
    fk_queries = dict(restore.FK_ORPHAN_QUERIES)

    def fake_query_scalar(sql: str) -> str:
        for needle, value in overrides.items():
            if needle in sql:
                return value

        for table in essential_tables:
            if f"table_name='{table}'" in sql and "information_schema.tables" in sql:
                return "0" if table in missing_tables else "1"

        if "information_schema.tables" in sql and "count(*)" in sql:
            return "9"

        if "count(DISTINCT code)" in sql and "markets" in sql:
            return "2"

        for name, fk_sql in fk_queries.items():
            if fk_sql.strip() == sql.strip() or fk_sql in sql:
                return fk_values.get(name, "0")

        for table in essential_tables:
            if f"FROM public.{table};" in sql and "count(*)" in sql:
                return row_counts.get(table, "2")

        raise AssertionError(f"unexpected SQL in fake query_scalar: {sql!r}")

    return fake_query_scalar


class TestVerifyRestoredIntegrity(unittest.TestCase):
    def test_verify_restored_integrity_passes_on_valid_synthetic_dataset(self):
        fake = _make_query_scalar()
        summary = restore.verify_restored_integrity(fake)
        self.assertEqual(summary["table_count"], 9)
        self.assertEqual(summary["fk_checks_passed"], len(restore.FK_ORPHAN_QUERIES))

    def test_verify_restored_integrity_fails_on_missing_essential_table(self):
        fake = _make_query_scalar(missing_tables={"orders"})
        with self.assertRaises(RuntimeError) as ctx:
            restore.verify_restored_integrity(fake)
        self.assertIn("orders", str(ctx.exception))

    def test_verify_restored_integrity_fails_on_insufficient_rows(self):
        fake = _make_query_scalar(row_counts={"products": "1"})
        with self.assertRaises(RuntimeError) as ctx:
            restore.verify_restored_integrity(fake)
        self.assertIn("products", str(ctx.exception))

    def test_verify_restored_integrity_fails_on_fk_orphan_or_cross_market(self):
        for fk_name in ("orders_cross_market_client", "order_items_missing_order"):
            with self.subTest(fk=fk_name):
                fake = _make_query_scalar(fk_values={fk_name: "1"})
                with self.assertRaises(RuntimeError):
                    restore.verify_restored_integrity(fake)


if __name__ == "__main__":
    unittest.main()
