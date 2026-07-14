"""Backup verificavel do PostgreSQL do Projeto Ilya.

O script usa a imagem oficial do PostgreSQL no Docker para evitar depender de
pg_dump instalado no Windows. Credenciais nunca sao gravadas no comando nem no
arquivo: a URL de producao e lida de PRODUCTION_DATABASE_URL.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "backups" / "database"
POSTGRES_IMAGE = "postgres:18-alpine"
STAMP_RE = re.compile(r"ilya-(local|production)-(\d{8}T\d{6})")


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, cwd=ROOT, **kwargs)


def openssl_path() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    git_openssl = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "openssl.exe"
    return str(git_openssl) if git_openssl.exists() else None


def dump_command(target: str) -> list[str]:
    if target == "local":
        return [
            "docker", "compose", "exec", "-T", "db", "pg_dump",
            "-U", "postgres", "-d", "ilya_db", "-Fc", "--no-owner", "--no-acl",
        ]
    if not os.environ.get("PRODUCTION_DATABASE_URL"):
        raise RuntimeError("Defina PRODUCTION_DATABASE_URL no ambiente para o backup de producao.")
    return [
        "docker", "run", "--rm", "-e", "PRODUCTION_DATABASE_URL",
        POSTGRES_IMAGE, "sh", "-c",
        'pg_dump "$PRODUCTION_DATABASE_URL" -Fc --no-owner --no-acl',
    ]


def create_dump(target: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".partial")
    try:
        with partial.open("wb") as output:
            result = subprocess.run(
                dump_command(target),
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"pg_dump falhou: {message}")
        if partial.stat().st_size < 1024 or partial.read_bytes()[:5] != b"PGDMP":
            raise RuntimeError("O arquivo gerado nao e um dump PostgreSQL valido.")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def verify_catalog(dump_path: Path) -> None:
    mount = f"{dump_path.parent.resolve()}:/backups:ro"
    result = subprocess.run(
        ["docker", "run", "--rm", "-v", mount, POSTGRES_IMAGE,
         "pg_restore", "--list", f"/backups/{dump_path.name}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode or b"TABLE" not in result.stdout:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"A verificacao do catalogo do backup falhou: {error}")


def encrypt(dump_path: Path) -> Path:
    password = os.environ.get("BACKUP_ENCRYPTION_PASSWORD")
    if not password:
        raise RuntimeError("Defina BACKUP_ENCRYPTION_PASSWORD para criptografar o backup.")
    executable = openssl_path()
    if not executable:
        raise RuntimeError("OpenSSL nao foi encontrado. Instale Git for Windows ou OpenSSL.")
    encrypted = dump_path.with_suffix(dump_path.suffix + ".enc")
    env = os.environ.copy()
    run([
        executable, "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000",
        "-in", str(dump_path), "-out", str(encrypted),
        "-pass", "env:BACKUP_ENCRYPTION_PASSWORD",
    ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if encrypted.stat().st_size <= dump_path.stat().st_size:
        encrypted.unlink(missing_ok=True)
        raise RuntimeError("A criptografia nao produziu um arquivo valido.")
    dump_path.unlink()
    return encrypted


def write_checksum(path: Path) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest.hexdigest()}  {path.name}\n", encoding="ascii"
    )


def apply_gfs_retention(folder: Path, target: str) -> list[Path]:
    """Mantem 7 dias, 4 semanas e 6 meses, sem apagar o backup recem-criado."""
    candidates: list[tuple[datetime, Path]] = []
    for path in folder.glob(f"ilya-{target}-*.dump*"):
        if path.suffix == ".sha256" or ".partial" in path.name:
            continue
        match = STAMP_RE.search(path.name)
        if match:
            candidates.append((datetime.strptime(match.group(2), "%Y%m%dT%H%M%S"), path))
    candidates.sort(reverse=True)
    now = datetime.now()
    keep: set[Path] = {path for stamp, path in candidates if stamp >= now - timedelta(days=7)}
    weekly: set[tuple[int, int]] = set()
    monthly: set[tuple[int, int]] = set()
    for stamp, path in candidates:
        iso = stamp.isocalendar()
        week = (iso.year, iso.week)
        month = (stamp.year, stamp.month)
        if len(weekly) < 4 and week not in weekly:
            weekly.add(week)
            keep.add(path)
        if len(monthly) < 6 and month not in monthly:
            monthly.add(month)
            keep.add(path)
    removed: list[Path] = []
    for _, path in candidates:
        if path not in keep:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".sha256").unlink(missing_ok=True)
            removed.append(path)
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "production"), default="local")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-unencrypted", action="store_true",
                        help="Permite backup sem criptografia (somente ambiente controlado).")
    parser.add_argument("--no-retention", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    encrypted = bool(os.environ.get("BACKUP_ENCRYPTION_PASSWORD"))
    if args.target == "production" and not encrypted and not args.allow_unencrypted:
        raise RuntimeError(
            "Backup de producao exige BACKUP_ENCRYPTION_PASSWORD. "
            "Use --allow-unencrypted apenas em armazenamento protegido."
        )
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dump_path = args.output_dir / f"ilya-{args.target}-{stamp}.dump"
    print(f"Criando backup {args.target}...")
    create_dump(args.target, dump_path)
    verify_catalog(dump_path)
    final_path = encrypt(dump_path) if encrypted else dump_path
    write_checksum(final_path)
    removed = [] if args.no_retention else apply_gfs_retention(args.output_dir, args.target)
    print(f"Backup verificado: {final_path}")
    print(f"SHA-256: {final_path.with_suffix(final_path.suffix + '.sha256')}")
    if removed:
        print(f"Retencao: {len(removed)} backup(s) antigo(s) removido(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
