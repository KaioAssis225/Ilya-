"""Backups e scripts de producao: TLS obrigatorio e nada em texto puro no share.

O repositorio fica num drive de rede (X:). Dump e export de producao so podem
chegar la depois de cifrados, e toda conexao ao Postgres publico do Railway
precisa exigir TLS (o padrao do libpq, `prefer`, aceita texto puro).
"""

from __future__ import annotations

import importlib.util
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock


OPS = Path(__file__).resolve().parent
ROOT = OPS.parent
PRODUCTION_PS1 = (
    "abrir-portugal.ps1",
    "inventario-eu.ps1",
    "investigar-tipo-orfao.ps1",
    "liberar-eu-e-tipos.ps1",
    "plano-catalogo-eu.ps1",
    "separar-catalogo-eu.ps1",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_database = _load("ops_backup_database_module", OPS / "backup_database.py")
backup_site = _load("ops_backup_site_module", ROOT / "backup_site.py")

_URL = "postgresql://postgres:segredo@host.proxy.rlwy.net:5432/railway"


class RequireTlsTest(unittest.TestCase):
    def test_missing_or_weak_sslmode_becomes_require(self):
        for url in (_URL, _URL + "?sslmode=prefer", _URL + "?sslmode=disable", _URL + "?sslmode=allow"):
            with self.subTest(url=url):
                self.assertIn("sslmode=require", backup_database.require_tls(url))
                self.assertNotRegex(backup_database.require_tls(url), r"sslmode=(prefer|disable|allow)")

    def test_stronger_modes_and_other_params_are_kept(self):
        url = _URL + "?sslmode=verify-full&sslrootcert=/certs/railway.pem&connect_timeout=10"
        result = backup_database.require_tls(url)
        self.assertIn("sslmode=verify-full", result)
        self.assertIn("sslrootcert=%2Fcerts%2Frailway.pem", result)
        self.assertIn("connect_timeout=10", result)

    def test_production_dump_runs_with_tls_url(self):
        with mock.patch.dict(os.environ, {"PRODUCTION_DATABASE_URL": _URL}):
            env = backup_database.dump_env("production")
        self.assertIn("sslmode=require", env["PRODUCTION_DATABASE_URL"])


class StagingTest(unittest.TestCase):
    def test_plaintext_dump_never_touches_output_dir(self):
        output = Path(tempfile.mkdtemp())
        seen: list[Path] = []

        def fake_dump(_target, destination):
            seen.append(destination)
            destination.write_bytes(b"PGDMP" + b"0" * 2048)

        def fake_encrypt(dump_path):
            encrypted = dump_path.with_suffix(dump_path.suffix + ".enc")
            encrypted.write_bytes(b"cifrado" * 400)
            dump_path.unlink()
            return encrypted

        argv = ["backup_database.py", "--target", "production", "--output-dir", str(output), "--no-retention"]
        env = {"PRODUCTION_DATABASE_URL": _URL, "BACKUP_ENCRYPTION_PASSWORD": "x"}
        with mock.patch.dict(os.environ, env), mock.patch("sys.argv", argv), \
                mock.patch.object(backup_database, "create_dump", fake_dump), \
                mock.patch.object(backup_database, "verify_catalog", lambda _p: None), \
                mock.patch.object(backup_database, "encrypt", fake_encrypt):
            self.assertEqual(backup_database.main(), 0)

        self.assertFalse(seen[0].resolve().is_relative_to(output.resolve()))
        names = sorted(p.name for p in output.iterdir())
        self.assertEqual(len(names), 2, names)
        self.assertTrue(names[0].endswith(".dump.enc"))
        self.assertTrue(names[1].endswith(".dump.enc.sha256"))
        self.assertFalse(seen[0].parent.exists(), "staging local deve ser removido")

    def test_site_export_is_staged_outside_repository(self):
        self.assertFalse(backup_site.BACKUP_DIR.resolve().is_relative_to(ROOT.resolve()))
        self.assertEqual(backup_site.OUTPUT_DIR.resolve(), (ROOT / "backups").resolve())


class PowerShellTlsTest(unittest.TestCase):
    def test_production_psql_scripts_require_tls(self):
        for name in PRODUCTION_PS1:
            with self.subTest(script=name):
                text = (OPS / name).read_text(encoding="utf-8")
                self.assertRegex(text, r"-e PGSSLMODE=require\b")

    def test_secret_setup_rejects_weak_sslmode(self):
        text = (OPS / "set-backup-secrets.ps1").read_text(encoding="utf-8")
        self.assertTrue(re.search(r"sslmode=\(disable\|allow\|prefer\)", text), text[:200])


if __name__ == "__main__":
    unittest.main()
