"""Copia o PostgreSQL do Estoque (Railway) para um banco novo e privado na VPS.

Mesmo padrão de ops/copy_railway_to_vps.py (Ilya): dump consistente e somente
leitura, lock_timeout curto, validação e UM BANCO NOVO por execução
(`estoque_copy_<carimbo>_<hex>` dentro do container `ilya-estoque-pg`). Nunca
escreve na origem e nunca toca nos bancos existentes.

Execute com o Python do projeto (3.12), Docker local e a chave SSH da VPS.

Duas formas de alcançar o Postgres do Estoque no Railway:

  A) Com URL (proxy TCP público):
       $env:ESTOQUE_PRODUCTION_DATABASE_URL = "<URL>"   # do cofre, nunca do chat
       python ops/hostgator/copy_estoque_to_vps.py root@IP-da-VPS

  B) Sem proxy público, por SSH nativo do Railway (chave TEMPORÁRIA que o próprio
     dono cadastra no Railway e revoga ao terminar). O pg_dump roda DENTRO do
     container do Postgres e só o dump trafega; nenhuma senha passa por aqui:
       python ops/hostgator/copy_estoque_to_vps.py root@IP-da-VPS \\
         --railway-ssh <instance-id>@ssh.railway.com --railway-key <chave-temporaria>

Saída: tempo de cada etapa (dump, verificação, transferência+restauração,
validação). A soma estima a janela de gravações pausadas.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_database import POSTGRES_IMAGE, require_tls, verify_catalog  # noqa: E402

PGOPTIONS = "-c default_transaction_read_only=on -c lock_timeout=3000 -c statement_timeout=0"

# Roda no Postgres do Railway: usa as variáveis PG*/POSTGRES_* que o próprio serviço tem.
REMOTE_DUMP = (
    'export PGOPTIONS="$1"; '
    'export PGPASSWORD="${PGPASSWORD:-$POSTGRES_PASSWORD}"; '
    'exec pg_dump -U "${PGUSER:-${POSTGRES_USER:-postgres}}" '
    '-d "${PGDATABASE:-${POSTGRES_DB:-railway}}" -Fc --no-owner --no-acl'
)

# Roda na VPS. Lê o dump em stdin e cria um banco novo. Em caso de erro, remove SÓ o
# banco que esta execução acabou de criar (nunca outro).
RESTORE_SCRIPT = """\
set -eu
database=$1
container=ilya-estoque-pg
docker exec "$container" createdb -U postgres "$database"
trap 'docker exec "$container" dropdb -U postgres "$database"' EXIT
docker exec -i "$container" pg_restore -U postgres -d "$database" \\
    --no-owner --no-acl --single-transaction --exit-on-error
trap - EXIT
"""

COUNT_SQL = """
SELECT 'schema_version', version_num FROM public.alembic_version;
SELECT 'tabelas_public', count(*) FROM pg_tables WHERE schemaname = 'public';
SELECT 'linhas:' || relname, (xpath('/row/c/text()',
       query_to_xml(format('SELECT count(*) AS c FROM public.%I', relname), false, true, '')))[1]::text
FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
  AND relname IN ('users','products','orders','stock_permissions','security_audit_events')
ORDER BY 1;
"""


def ssh_base(identity: Path, port: int) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o",
            "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-i", str(identity),
            "-p", str(port)]


def timed(label: str, timings: dict[str, float], started: float) -> None:
    timings[label] = time.monotonic() - started
    print(f"  [{timings[label]:7.1f}s] {label}", flush=True)


def dump_to(path: Path, args: argparse.Namespace) -> None:
    if args.railway_ssh:
        command = [*ssh_base(args.railway_key, 22), "-T", args.railway_ssh,
                   "sh", "-c", shlex.quote(REMOTE_DUMP), "dump", shlex.quote(PGOPTIONS)]
        env = os.environ.copy()
    else:
        url = os.environ.get("ESTOQUE_PRODUCTION_DATABASE_URL")
        if not url:
            raise RuntimeError("Defina ESTOQUE_PRODUCTION_DATABASE_URL (ou use --railway-ssh).")
        env = os.environ.copy()
        env["ESTOQUE_PRODUCTION_DATABASE_URL"] = require_tls(url)
        env["PGOPTIONS"] = PGOPTIONS
        command = ["docker", "run", "--rm", "-e", "ESTOQUE_PRODUCTION_DATABASE_URL", "-e", "PGOPTIONS",
                   POSTGRES_IMAGE, "sh", "-c",
                   'pg_dump "$ESTOQUE_PRODUCTION_DATABASE_URL" -Fc --no-owner --no-acl']
    partial = path.with_suffix(".partial")
    try:
        with partial.open("wb") as output:
            result = subprocess.run(command, env=env, stdout=output,
                                    stderr=subprocess.PIPE, check=False)
        if result.returncode:
            # O stderr do pg_dump/ssh não contém a senha (só mensagens de erro).
            raise RuntimeError("pg_dump falhou: "
                               + result.stderr.decode("utf-8", errors="replace").strip())
        if partial.stat().st_size < 1024 or partial.read_bytes()[:5] != b"PGDMP":
            raise RuntimeError("O arquivo gerado não é um dump PostgreSQL válido.")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host", help="Destino SSH da VPS, por exemplo root@IP")
    parser.add_argument("--port", type=int, default=22022)
    parser.add_argument("--identity-file", type=Path,
                        default=Path.home() / ".ssh" / "ilya_hostgator_vps_ed25519")
    parser.add_argument("--railway-ssh", help="alvo SSH nativo do Railway (instância do Postgres)")
    parser.add_argument("--railway-key", type=Path, help="chave TEMPORÁRIA cadastrada no Railway")
    args = parser.parse_args()
    if args.railway_ssh and not args.railway_key:
        parser.error("--railway-ssh exige --railway-key")

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    database = f"estoque_copy_{stamp}_{secrets.token_hex(4)}"
    ssh = [*ssh_base(args.identity_file, args.port), "--", args.host]
    timings: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="estoque-vps-copy-") as temporary:
        dump = Path(temporary) / "copy.dump"
        print("Gerando backup consistente do Estoque (somente leitura)...", flush=True)
        started = time.monotonic()
        dump_to(dump, args)
        timed("cópia (pg_dump)", timings, started)
        print(f"  dump: {dump.stat().st_size / 1_048_576:.0f} MiB", flush=True)

        started = time.monotonic()
        verify_catalog(dump)
        timed("verificação do dump", timings, started)

        print(f"Transferindo e restaurando {database} na VPS...", flush=True)
        started = time.monotonic()
        with dump.open("rb") as stream:
            remote = shlex.join(["bash", "-c", RESTORE_SCRIPT, "restore", database])
            subprocess.run([*ssh, remote], stdin=stream, check=True)
        timed("transferência + restauração", timings, started)

        started = time.monotonic()
        counts = subprocess.run(
            [*ssh, shlex.join(["docker", "exec", "-i", "ilya-estoque-pg", "psql", "-X", "-At",
                               "-F", " = ", "-U", "postgres", "-d", database,
                               "-v", "ON_ERROR_STOP=1"])],
            input=COUNT_SQL, text=True, capture_output=True, check=True,
        ).stdout
        timed("validação (contagens)", timings, started)
    print(counts.rstrip())
    print(f"Total medido: {sum(timings.values()):.1f}s")
    print(f"Cópia validada na VPS: {database}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Falha na cópia: {exc}", file=sys.stderr)
        raise SystemExit(1)
