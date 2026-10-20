"""Restaura um dump do Ilya em PostgreSQL temporario e descartavel (Bloco P17).

O banco local e o banco de producao nunca sao alterados. Ao final, mesmo em
caso de erro, o container temporario e removido.

Alinhamento de versao PostgreSQL (origem/destino):
  - Por padrao utiliza `postgres:16-alpine` (alinhado com `docker-compose.test.yml`
    e CI `postgres:16-alpine`), ou detecta automaticamente a versao principal no
    cabecalho do dump (`-- Dumped from database version <major>.<minor>`, ex.:
    PG16 -> `postgres:16-alpine`, PG18 -> `postgres:18-alpine`).
  - Pode ser sobrescrito via `--postgres-image` ou `RESTORE_POSTGRES_IMAGE`.

Verificacao de integridade (alem do checksum SHA-256):
  - Tabelas essenciais presentes no schema `public`.
  - Contagem minima de linhas por tabela conhecida do dataset sintetico.
  - Integridade referencial / ausencia de orfaos em FKs e ausencia de mistura
    cruzada BR/EU entre pedidos e clientes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


DEFAULT_POSTGRES_IMAGE = "postgres:16-alpine"
POSTGRES_IMAGE = DEFAULT_POSTGRES_IMAGE

ESSENTIAL_TABLES: tuple[str, ...] = (
    "markets",
    "users",
    "user_markets",
    "catalogs",
    "products",
    "product_markets",
    "clients",
    "orders",
    "order_items",
)

EXPECTED_MIN_ROWS: dict[str, int] = {t: 2 for t in ESSENTIAL_TABLES}

FK_ORPHAN_QUERIES: dict[str, str] = {
    "user_markets_missing_user": (
        "SELECT count(*) FROM public.user_markets um "
        "LEFT JOIN public.users u ON u.id = um.user_id "
        "WHERE u.id IS NULL;"
    ),
    "user_markets_missing_market": (
        "SELECT count(*) FROM public.user_markets um "
        "LEFT JOIN public.markets m ON m.code = um.market_code "
        "WHERE m.code IS NULL;"
    ),
    "catalogs_missing_market": (
        "SELECT count(*) FROM public.catalogs c "
        "LEFT JOIN public.markets m ON m.code = c.market_code "
        "WHERE m.code IS NULL;"
    ),
    "products_missing_catalog": (
        "SELECT count(*) FROM public.products p "
        "LEFT JOIN public.catalogs c ON c.id = p.catalog_id "
        "WHERE c.id IS NULL;"
    ),
    "product_markets_missing_product": (
        "SELECT count(*) FROM public.product_markets pm "
        "LEFT JOIN public.products p ON p.id = pm.product_id "
        "WHERE p.id IS NULL;"
    ),
    "product_markets_missing_market": (
        "SELECT count(*) FROM public.product_markets pm "
        "LEFT JOIN public.markets m ON m.code = pm.market_code "
        "WHERE m.code IS NULL;"
    ),
    "clients_missing_market": (
        "SELECT count(*) FROM public.clients cl "
        "LEFT JOIN public.markets m ON m.code = cl.market_code "
        "WHERE m.code IS NULL;"
    ),
    "orders_missing_client": (
        "SELECT count(*) FROM public.orders o "
        "LEFT JOIN public.clients cl ON cl.id = o.client_id "
        "WHERE cl.id IS NULL;"
    ),
    "orders_cross_market_client": (
        "SELECT count(*) FROM public.orders o "
        "JOIN public.clients cl ON cl.id = o.client_id "
        "WHERE o.market_code <> cl.market_code;"
    ),
    "order_items_missing_order": (
        "SELECT count(*) FROM public.order_items oi "
        "LEFT JOIN public.orders o ON o.id = oi.order_id "
        "WHERE o.id IS NULL;"
    ),
    "order_items_missing_product": (
        "SELECT count(*) FROM public.order_items oi "
        "LEFT JOIN public.products p ON p.id = oi.product_id "
        "WHERE p.id IS NULL;"
    ),
}


def verify_checksum(source: Path | str) -> None:
    source = Path(source)
    checksum_file = source.with_suffix(source.suffix + ".sha256")
    if not checksum_file.is_file():
        raise RuntimeError(f"Checksum ausente: {checksum_file}")
    expected = checksum_file.read_text(encoding="ascii").split()[0].lower()
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        if source.suffix == ".sql":
            lf_digest = hashlib.sha256(
                source.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            if lf_digest == expected:
                return
        raise RuntimeError(
            "SHA-256 divergente: o backup pode estar corrompido ou adulterado."
        )


def openssl_path() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    candidate = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git"
        / "usr"
        / "bin"
        / "openssl.exe"
    )
    return str(candidate) if candidate.exists() else None


def decrypt_if_needed(source: Path, temp_dir: Path) -> Path:
    if source.suffix != ".enc":
        return source
    password = os.environ.get("BACKUP_ENCRYPTION_PASSWORD")
    executable = openssl_path()
    if not password or not executable:
        raise RuntimeError(
            "Para testar arquivo .enc, defina BACKUP_ENCRYPTION_PASSWORD e disponibilize OpenSSL."
        )
    destination = temp_dir / source.name.removesuffix(".enc")
    env = os.environ.copy()
    subprocess.run(
        [
            executable,
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-in",
            str(source),
            "-out",
            str(destination),
            "-pass",
            "env:BACKUP_ENCRYPTION_PASSWORD",
        ],
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return destination


def docker(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=True, **kwargs)


def detect_dump_pg_major(source: Path | str) -> int | None:
    source = Path(source)
    if source.suffix == ".enc":
        return None
    try:
        with source.open("rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    text = head.decode("utf-8", errors="ignore")
    match = re.search(r"Dumped from database version (\d+)", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def resolve_postgres_image(
    source: Path | str, explicit_image: str | None = None
) -> str:
    if explicit_image:
        return explicit_image
    env_image = os.environ.get("RESTORE_POSTGRES_IMAGE", "").strip()
    if env_image:
        return env_image
    major = detect_dump_pg_major(source)
    if major is not None:
        return f"postgres:{major}-alpine"
    return DEFAULT_POSTGRES_IMAGE


def query_scalar(sql: str) -> str:
    raise RuntimeError(
        "query_scalar requer um container PostgreSQL em execucao ou injecao nos testes."
    )


def verify_restored_integrity(
    runner: Callable[[str], str] | None = None,
    expected_min_rows: dict[str, int] | None = None,
) -> dict[str, Any]:
    run_sql = runner or query_scalar
    if expected_min_rows is None:
        expected_min_rows = EXPECTED_MIN_ROWS

    table_count_raw = run_sql(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE';"
    )
    table_count = int(table_count_raw.strip())
    if table_count == 0:
        raise RuntimeError("Restauracao terminou sem tabelas no schema public.")

    missing_tables: list[str] = []
    for table in ESSENTIAL_TABLES:
        exists_raw = run_sql(
            f"SELECT count(*) FROM information_schema.tables "
            f"WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name='{table}';"
        )
        if int(exists_raw.strip()) < 1:
            missing_tables.append(table)
    if missing_tables:
        raise RuntimeError(
            f"Tabelas essenciais ausentes apos restore: {', '.join(missing_tables)}"
        )

    row_counts: dict[str, int] = {}
    for table in ESSENTIAL_TABLES:
        count_raw = run_sql(f"SELECT count(*) FROM public.{table};")
        count = int(count_raw.strip())
        row_counts[table] = count
        min_rows = expected_min_rows.get(table, 0)
        if count < min_rows:
            raise RuntimeError(
                f"Tabela {table} possui {count} linha(s), abaixo do minimo esperado ({min_rows})."
            )

    for check_name, fk_sql in FK_ORPHAN_QUERIES.items():
        orphans = int(run_sql(fk_sql).strip())
        if orphans != 0:
            raise RuntimeError(
                f"Violacao de integridade referencial/mercado ({check_name}): {orphans} registro(s)."
            )

    distinct_markets = int(
        run_sql(
            "SELECT count(DISTINCT code) FROM public.markets WHERE code IN ('BR', 'EU');"
        ).strip()
    )
    if distinct_markets != 2:
        raise RuntimeError(
            f"Esperados 2 mercados distintos (BR, EU), encontrados: {distinct_markets}."
        )

    return {
        "table_count": table_count,
        "row_counts": row_counts,
        "fk_checks_passed": len(FK_ORPHAN_QUERIES),
    }


def _looks_like_custom_dump(source: Path) -> bool:
    try:
        with source.open("rb") as fh:
            return fh.read(5) == b"PGDMP"
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument(
        "--postgres-image",
        default=None,
        help="Imagem Docker do PostgreSQL (padrao: auto-detecta versao do dump ou postgres:16-alpine).",
    )
    args = parser.parse_args(argv)
    source = args.backup.resolve()
    if not source.is_file():
        raise RuntimeError(f"Backup nao encontrado: {source}")
    verify_checksum(source)

    name = f"ilya-restore-test-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="ilya-restore-") as temporary:
        dump = decrypt_if_needed(source, Path(temporary))
        image = resolve_postgres_image(dump, args.postgres_image)
        try:
            docker(
                "run",
                "-d",
                "--name",
                name,
                "-e",
                f"POSTGRES_PASSWORD={password}",
                image,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(30):
                ready = subprocess.run(
                    ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(
                    "PostgreSQL temporario nao ficou pronto em 30 segundos."
                )

            docker(
                "exec",
                name,
                "createdb",
                "-U",
                "postgres",
                "ilya_restore",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            with dump.open("rb") as backup_stream:
                if _looks_like_custom_dump(dump):
                    restored = subprocess.run(
                        [
                            "docker",
                            "exec",
                            "-i",
                            name,
                            "pg_restore",
                            "-U",
                            "postgres",
                            "-d",
                            "ilya_restore",
                            "--no-owner",
                            "--no-acl",
                            "--exit-on-error",
                        ],
                        stdin=backup_stream,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                else:
                    restored = subprocess.run(
                        [
                            "docker",
                            "exec",
                            "-i",
                            name,
                            "psql",
                            "-U",
                            "postgres",
                            "-d",
                            "ilya_restore",
                            "-v",
                            "ON_ERROR_STOP=1",
                        ],
                        stdin=backup_stream,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
            if restored.returncode:
                raise RuntimeError(
                    restored.stderr.decode("utf-8", errors="replace")
                )

            def _run_psql_scalar(sql: str) -> str:
                res = docker(
                    "exec",
                    name,
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    "ilya_restore",
                    "-Atc",
                    sql,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                return res.stdout.strip()

            summary = verify_restored_integrity(_run_psql_scalar)
            print(
                f"Restauracao isolada aprovada ({image}): "
                f"{summary['table_count']} tabela(s), "
                f"{summary['fk_checks_passed']} verificacoes de FK/mercado sem orfaos."
            )
            return 0
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
