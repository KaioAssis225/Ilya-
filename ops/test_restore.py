"""Restaura um dump do Ilya em PostgreSQL temporario e descartavel.

O banco local e o banco de producao nunca sao alterados. Ao final, mesmo em
caso de erro, o container temporario e removido.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


POSTGRES_IMAGE = "postgres:18-alpine"


def verify_checksum(source: Path) -> None:
    checksum_file = source.with_suffix(source.suffix + ".sha256")
    if not checksum_file.is_file():
        raise RuntimeError(f"Checksum ausente: {checksum_file}")
    expected = checksum_file.read_text(encoding="ascii").split()[0].lower()
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise RuntimeError("SHA-256 divergente: o backup pode estar corrompido ou adulterado.")


def openssl_path() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "openssl.exe"
    return str(candidate) if candidate.exists() else None


def decrypt_if_needed(source: Path, temp_dir: Path) -> Path:
    if source.suffix != ".enc":
        return source
    password = os.environ.get("BACKUP_ENCRYPTION_PASSWORD")
    executable = openssl_path()
    if not password or not executable:
        raise RuntimeError("Para testar arquivo .enc, defina BACKUP_ENCRYPTION_PASSWORD e disponibilize OpenSSL.")
    destination = temp_dir / source.name.removesuffix(".enc")
    env = os.environ.copy()
    subprocess.run([
        executable, "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
        "-in", str(source), "-out", str(destination),
        "-pass", "env:BACKUP_ENCRYPTION_PASSWORD",
    ], env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return destination


def docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    source = args.backup.resolve()
    if not source.is_file():
        raise RuntimeError(f"Backup nao encontrado: {source}")
    verify_checksum(source)

    name = f"ilya-restore-test-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="ilya-restore-") as temporary:
        dump = decrypt_if_needed(source, Path(temporary))
        try:
            docker("run", "-d", "--name", name,
                   "-e", f"POSTGRES_PASSWORD={password}", POSTGRES_IMAGE,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(30):
                ready = subprocess.run(
                    ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("PostgreSQL temporario nao ficou pronto em 30 segundos.")

            docker("exec", name, "createdb", "-U", "postgres", "ilya_restore",
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with dump.open("rb") as backup_stream:
                restored = subprocess.run([
                    "docker", "exec", "-i", name, "pg_restore", "-U", "postgres",
                    "-d", "ilya_restore", "--no-owner", "--no-acl", "--exit-on-error",
                ], stdin=backup_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if restored.returncode:
                raise RuntimeError(restored.stderr.decode("utf-8", errors="replace"))
            query = (
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE';"
            )
            result = docker("exec", name, "psql", "-U", "postgres", "-d", "ilya_restore",
                            "-Atc", query, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            table_count = int(result.stdout.strip())
            if table_count == 0:
                raise RuntimeError("Restauracao terminou sem tabelas no schema public.")
            print(f"Restauracao isolada aprovada: {table_count} tabela(s) encontradas.")
            return 0
        finally:
            subprocess.run(["docker", "rm", "-f", name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
