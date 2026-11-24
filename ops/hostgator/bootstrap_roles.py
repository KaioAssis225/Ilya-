#!/usr/bin/env python3
"""Roles e GRANTs dos bancos da stack de produção. Roda NA VPS.

  bootstrap_roles.py roles    cria ilya_app, estoque_app e ilya_estoque_readonly,
                              ajusta donos e a extensão pg_trgm (ANTES do restore)
  bootstrap_roles.py grants   aplica os GRANTs da ilya_estoque_readonly (DEPOIS do restore)
  bootstrap_roles.py verify   prova, como a própria role, o que ela lê e o que não pode

Os GRANTs reproduzem a produção do Railway (ops/login_unico_estoque_grants.sql e
ops/estoque_grant_catalogs.py do checkout principal):

  products, orders, order_items   SELECT na tabela
  catalogs                        SELECT (id, market_code, name)
  users                           SELECT (id, email, username, full_name, is_active,
                                          must_change_password, auth_version,
                                          has_stock_access)
  user_markets                    SELECT (user_id, market_code, role, status)

`hashed_password` NUNCA é liberado. Nenhuma senha é impressa: elas vêm de
env/roles.env (0600) e entram no SQL só por stdin / variável de ambiente.

Diretório da stack: /opt/ilya-production (ou ILYA_PRODUCTION_ROOT).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ILYA_PRODUCTION_ROOT", "/opt/ilya-production"))

RO_ROLE = "ilya_estoque_readonly"

USERS_COLS = (
    "id", "email", "username", "full_name", "is_active",
    "must_change_password", "auth_version", "has_stock_access",
)
USER_MARKETS_COLS = ("user_id", "market_code", "role", "status")
CATALOGS_COLS = ("id", "market_code", "name")
FULL_TABLES = ("products", "orders", "order_items")


def read_roles() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "env" / "roles.env").read_text(encoding="utf-8").splitlines():
        key, _, raw = line.partition("=")
        values[key] = raw.strip("'")
    for key, value in values.items():
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise SystemExit(f"{key}: formato inesperado (esperado hex de 64).")
    return values


def psql(service: str, database: str, sql: str, *, extra_env: dict[str, str] | None = None,
         user: str = "postgres", host: str | None = None,
         check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "exec", "-T"]
    env = dict(os.environ)
    if extra_env:
        for key, value in extra_env.items():
            cmd += ["-e", key]  # sem valor: o Docker copia do ambiente deste processo
            env[key] = value
    cmd += [service, "psql", "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1",
            "-X", "-q", "-A", "-t"]
    if host:
        cmd += ["-h", host]
    result = subprocess.run(cmd, input=sql, text=True, capture_output=True, cwd=ROOT, env=env)
    if check and result.returncode != 0:
        # O stderr do psql não contém senhas (só mensagens de erro de SQL/permissão).
        raise SystemExit(f"psql em {service}/{database} falhou:\n{result.stderr.strip()}")
    return result


def role_block(name: str, password: str) -> str:
    return f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{name}') THEN
    CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
ALTER ROLE {name} PASSWORD '{password}';
"""


def cmd_roles() -> None:
    roles = read_roles()
    psql(
        "ilya-db", "ilya",
        role_block("ilya_app", roles["ILYA_APP_PASSWORD"])
        + role_block(RO_ROLE, roles["ILYA_ESTOQUE_READONLY_PASSWORD"])
        + f"""
ALTER DATABASE ilya OWNER TO ilya_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
REVOKE ALL ON DATABASE ilya FROM PUBLIC;
GRANT CONNECT ON DATABASE ilya TO ilya_app, {RO_ROLE};
-- Defesa em profundidade: toda sessão desta role já nasce somente-leitura.
ALTER ROLE {RO_ROLE} SET default_transaction_read_only = on;
ALTER ROLE {RO_ROLE} SET statement_timeout = '30s';
""",
    )
    psql(
        "estoque-db", "estoque",
        role_block("estoque_app", roles["ESTOQUE_APP_PASSWORD"])
        + """
ALTER DATABASE estoque OWNER TO estoque_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
REVOKE ALL ON DATABASE estoque FROM PUBLIC;
GRANT CONNECT ON DATABASE estoque TO estoque_app;
""",
    )
    print("roles: ilya_app, ilya_estoque_readonly (ilya) e estoque_app (estoque) prontas.")


def cmd_grants() -> None:
    users = ", ".join(USERS_COLS)
    markets = ", ".join(USER_MARKETS_COLS)
    catalogs = ", ".join(CATALOGS_COLS)
    tables = ", ".join(FULL_TABLES)
    psql("ilya-db", "ilya", f"""
BEGIN;
-- Recomeça do zero para o resultado não depender do que já havia.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RO_ROLE};
GRANT USAGE ON SCHEMA public TO {RO_ROLE};
GRANT SELECT ON {tables} TO {RO_ROLE};
GRANT SELECT ({catalogs}) ON catalogs TO {RO_ROLE};
GRANT SELECT ({users}) ON users TO {RO_ROLE};
GRANT SELECT ({markets}) ON user_markets TO {RO_ROLE};
COMMIT;
""")
    print("grants: aplicados em ilya_estoque_readonly.")


def expect(label: str, ok: bool) -> bool:
    print(f"  [{'OK' if ok else 'FALHOU'}] {label}")
    return ok


def cmd_verify() -> int:
    roles = read_roles()
    env = {"PGPASSWORD": roles["ILYA_ESTOQUE_READONLY_PASSWORD"]}

    def as_ro(sql: str) -> subprocess.CompletedProcess:
        return psql("ilya-db", "ilya", sql, extra_env=env, user=RO_ROLE,
                    # Pelo nome do serviço (e não 127.0.0.1, que o pg_hba da imagem
                    # aceita como trust): assim a senha da role é exercitada de verdade.
                    host="ilya-db", check=False)

    print("ilya_estoque_readonly (conectando como a própria role):")
    good = True
    # O que PRECISA funcionar.
    for table in FULL_TABLES:
        good &= expect(f"SELECT em {table}",
                       as_ro(f"SELECT count(*) FROM {table};").returncode == 0)
    good &= expect(f"SELECT ({', '.join(CATALOGS_COLS)}) em catalogs",
                   as_ro(f"SELECT {', '.join(CATALOGS_COLS)} FROM catalogs LIMIT 1;").returncode == 0)
    good &= expect("SELECT das 8 colunas liberadas em users",
                   as_ro(f"SELECT {', '.join(USERS_COLS)} FROM users LIMIT 1;").returncode == 0)
    good &= expect("SELECT das 4 colunas liberadas em user_markets",
                   as_ro(f"SELECT {', '.join(USER_MARKETS_COLS)} FROM user_markets LIMIT 1;").returncode == 0)
    # O que PRECISA ser negado.
    denied = [
        ("ler users.hashed_password", "SELECT hashed_password FROM users LIMIT 1;"),
        ("SELECT * em users", "SELECT * FROM users LIMIT 1;"),
        ("SELECT * em user_markets", "SELECT * FROM user_markets LIMIT 1;"),
        ("INSERT em products", "INSERT INTO products DEFAULT VALUES;"),
        ("UPDATE em orders", "UPDATE orders SET id = id WHERE false;"),
        ("DELETE em order_items", "DELETE FROM order_items WHERE false;"),
        ("UPDATE em users", "UPDATE users SET is_active = is_active WHERE false;"),
        ("CREATE TABLE", "CREATE TABLE _ro_probe (x int);"),
        ("TRUNCATE products", "TRUNCATE products;"),
    ]
    for label, sql in denied:
        good &= expect(f"negado: {label}", as_ro(sql).returncode != 0)
    # Atributos da role e privilégios de escrita segundo o catálogo do Postgres.
    attrs = psql("ilya-db", "ilya", f"""
SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
FROM pg_roles WHERE rolname = '{RO_ROLE}';
SELECT count(*) FROM information_schema.role_table_grants
WHERE grantee = '{RO_ROLE}' AND privilege_type <> 'SELECT';
SELECT count(*) FROM information_schema.column_privileges
WHERE grantee = '{RO_ROLE}' AND table_name = 'users' AND column_name = 'hashed_password';
""").stdout.split()
    # Colunas liberadas == exatamente a lista de produção (se o catalogs ganhar uma
    # coluna nova, ela NÃO pode aparecer aqui sem decisão explícita).
    for table, expected in (("catalogs", CATALOGS_COLS), ("users", USERS_COLS),
                            ("user_markets", USER_MARKETS_COLS)):
        got = psql("ilya-db", "ilya", f"""
SELECT column_name FROM information_schema.column_privileges
WHERE grantee = '{RO_ROLE}' AND table_name = '{table}' AND privilege_type = 'SELECT'
ORDER BY column_name;
""").stdout.split()
        good &= expect(f"colunas liberadas em {table} == lista de produção",
                       sorted(got) == sorted(expected))
    good &= expect("sem atributos especiais (superuser/createdb/createrole/replication/bypassrls)",
                   attrs[0] == "f")
    good &= expect("nenhum privilégio de escrita em nenhuma tabela", attrs[1] == "0")
    good &= expect("hashed_password ausente dos privilégios de coluna", attrs[2] == "0")
    print("RESULTADO:", "tudo certo" if good else "HÁ FALHAS")
    return 0 if good else 1


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"roles", "grants", "verify"}:
        raise SystemExit(__doc__)
    if sys.argv[1] == "roles":
        cmd_roles()
    elif sys.argv[1] == "grants":
        cmd_grants()
    else:
        return cmd_verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
