"""Copia o PostgreSQL de produção para um banco novo e privado na VPS.

Execute com Python 3.12, Docker local e uma chave SSH autorizada.
Defina PRODUCTION_DATABASE_URL no ambiente, como no backup de produção.
O destino é o container dedicado ilya-railway-copy-db, sem rede externa.
Cada execução cria um banco independente para validação.
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
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from backup_database import create_dump, verify_catalog


RESTORE_SCRIPT = """\
set -eu
database=$1
container=ilya-railway-copy-db
[ "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$container")" = none ]
docker exec "$container" createdb -U postgres "$database"
trap 'docker exec "$container" dropdb -U postgres "$database"' EXIT
docker exec -i "$container" pg_restore -U postgres -d "$database" \\
    --no-owner --no-acl --single-transaction --exit-on-error
docker exec "$container" psql -X -U postgres -d "$database" -v ON_ERROR_STOP=1 \\
    -c 'SELECT version_num AS schema_version FROM public.alembic_version;' \\
    -c 'SELECT (SELECT count(*) FROM public.users) AS users,
               (SELECT count(*) FROM public.clients) AS clients,
               (SELECT count(*) FROM public.products) AS products,
               (SELECT count(*) FROM public.orders) AS orders;'
trap - EXIT
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Destino SSH, por exemplo root@IP-da-VPS")
    parser.add_argument("--port", type=int, default=22022)
    parser.add_argument("--identity-file", type=Path,
                        default=Path.home() / ".ssh" / "ilya_hostgator_vps_ed25519")
    args = parser.parse_args()

    source = os.environ.get("PRODUCTION_DATABASE_URL")
    if not source:
        raise RuntimeError("Defina PRODUCTION_DATABASE_URL antes de executar.")
    url = urlsplit(source)
    query = dict(parse_qsl(url.query, keep_blank_values=True))
    options = query.get("options", "")
    query["options"] = f"{options} -c default_transaction_read_only=on -c lock_timeout=3000".strip()
    os.environ["PRODUCTION_DATABASE_URL"] = urlunsplit(url._replace(query=urlencode(query, quote_via=quote)))

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    database = f"ilya_copy_{stamp}_{secrets.token_hex(4)}"
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o",
           "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-i", str(args.identity_file),
           "-p", str(args.port), "--", args.host]
    with tempfile.TemporaryDirectory(prefix="ilya-vps-copy-") as temporary:
        dump = Path(temporary) / "copy.dump"
        print("Gerando backup consistente do Railway...", flush=True)
        started = time.monotonic()
        create_dump("production", dump)
        timings = {"cópia (pg_dump)": time.monotonic() - started}
        started = time.monotonic()
        verify_catalog(dump)
        timings["verificação do dump"] = time.monotonic() - started
        print(f"Restaurando {database} na VPS...", flush=True)
        started = time.monotonic()
        with dump.open("rb") as stream:
            remote = shlex.join(["bash", "-c", RESTORE_SCRIPT, "restore", database])
            subprocess.run([*ssh, remote], stdin=stream, check=True)
        timings["transferência + restauração + contagens"] = time.monotonic() - started
    for label, seconds in timings.items():
        print(f"  [{seconds:7.1f}s] {label}")
    print(f"Total medido: {sum(timings.values()):.1f}s")
    print(f"Cópia validada na VPS: {database}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Falha na cópia: {exc}", file=sys.stderr)
        raise SystemExit(1)
