#!/usr/bin/env python3
"""Gera os env files da stack de produção (/opt/ilya-production/env).

Roda NA VPS, como root. Lê a configuração coletada do Railway
(/opt/ilya-cutover/config/{ilya,ilya-email,estoque}.json) e grava:

  env/ilya-api.env      API + migração do Ilya
  env/ilya-email.env    worker de e-mail do Ilya
  env/estoque.env       API, worker e migração do Estoque
  env/ilya-db.env, env/estoque-db.env, env/ilya-redis.env, env/estoque-redis.env
  env/roles.env         senhas das roles de banco (lidas só por bootstrap_roles.py)
  .env                  tags das imagens (não secreto)

Regras:
  * Segredos que precisam ser os mesmos de hoje (PASSWORD_PEPPER, SECRET_KEY, par de
    chaves do login único) são COPIADOS do Railway. Se trocarem, ninguém mais loga.
  * Senhas novas (bancos, Redis, roles) são geradas aqui, com `secrets`.
  * Nenhum valor é impresso: a saída lista só nomes e um hash curto.
  * Não sobrescreve arquivo existente (use --force por sua conta e risco: gerar de
    novo troca as senhas e o banco já criado deixa de aceitá-las).
  * ORDER_EMAIL_MODE fica `off`, Moloni e webhook desligados, e o sync automático
    do Estoque desligado até a virada.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

CONFIG_DIR = Path("/opt/ilya-cutover/config")
OUT_ROOT = Path("/opt/ilya-production")

# Banco e Redis desta stack. Os hosts são os nomes dos serviços do compose.yaml.
ILYA_DB, ILYA_APP_ROLE, ILYA_RO_ROLE = "ilya", "ilya_app", "ilya_estoque_readonly"
ESTOQUE_DB, ESTOQUE_APP_ROLE = "estoque", "estoque_app"

# Gateway da rede `edge` (172.29.10.0/24 no compose.yaml): é de lá que o Caddy, no
# host, chega às APIs. Só ele pode informar o IP real do cliente (X-Forwarded-For).
FORWARDED_ALLOW_IPS = "172.29.10.1"

# Segredos que NÃO podem ser regenerados: sem eles as contas deixam de logar.
MUST_PRESERVE_ILYA = (
    "PASSWORD_PEPPER",
    "SECRET_KEY",
    "STOCK_HANDOFF_PRIVATE_KEY",
    "STOCK_HANDOFF_KID",
)
MUST_PRESERVE_ESTOQUE = (
    "PASSWORD_PEPPER",
    "SECRET_KEY",
    "SECURITY_AUDIT_FINGERPRINT_KEY",
    "ILYA_HANDOFF_PUBLIC_KEYS",
)


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:6]


def load(config_dir: Path, name: str) -> dict[str, str]:
    path = config_dir / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: esperado um objeto JSON plano.")
    return {str(k): str(v) for k, v in data.items()}


def env_line(key: str, value: str) -> str:
    """Linha de env file do Compose. Aspas simples = valor literal (sem `$`)."""
    # PEM em uma linha com "\n" literal: o Ilya já trata isso (stock_handoff._load_key).
    value = value.replace("\r\n", "\n").replace("\n", "\\n")
    if "'" in value:
        raise SystemExit(f"{key}: valor com aspa simples não cabe no env file.")
    return f"{key}='{value}'\n"


def write_env(path: Path, values: dict[str, str], force: bool) -> bool:
    if path.exists() and not force:
        print(f"= {path.name}: já existe, mantido")
        return False
    lines = "".join(env_line(k, v) for k, v in values.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(lines)
    os.chmod(path, 0o600)
    print(f"+ {path.name}: {len(values)} variáveis")
    for key in sorted(values):
        print(f"    {key} [{short_hash(values[key])}]")
    return True


def require(source: dict[str, str], keys: tuple[str, ...], label: str) -> None:
    missing = [k for k in keys if not source.get(k)]
    if missing:
        raise SystemExit(f"{label}: faltam {', '.join(missing)} na configuração coletada.")


def password() -> str:
    return secrets.token_hex(32)  # hex: seguro em URL, sem escape


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--ilya-image", default="ilya-production-api:899ad3e0")
    parser.add_argument("--ilya-email-image", default="ilya-production-email:899ad3e0")
    parser.add_argument("--estoque-image", default="ilya-production-estoque:5c94f57")
    args = parser.parse_args()

    env_dir = args.out_root / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(env_dir, 0o700)

    ilya = load(args.config_dir, "ilya.json")
    ilya_email = load(args.config_dir, "ilya-email.json")
    estoque = load(args.config_dir, "estoque.json")
    require(ilya, MUST_PRESERVE_ILYA, "ilya.json")
    require(ilya_email, ("PASSWORD_PEPPER", "SECRET_KEY"), "ilya-email.json")
    require(estoque, MUST_PRESERVE_ESTOQUE, "estoque.json")

    # O worker de e-mail e a API precisam ter o MESMO pepper e a MESMA chave.
    for key in ("PASSWORD_PEPPER", "SECRET_KEY"):
        if ilya[key] != ilya_email[key]:
            raise SystemExit(f"{key} difere entre ilya.json e ilya-email.json.")
    # O kid que o Ilya assina precisa estar na lista pública do Estoque.
    try:
        public_keys = json.loads(estoque["ILYA_HANDOFF_PUBLIC_KEYS"])
    except json.JSONDecodeError as exc:
        raise SystemExit("ILYA_HANDOFF_PUBLIC_KEYS do Estoque não é JSON válido.") from exc
    if ilya["STOCK_HANDOFF_KID"] not in public_keys:
        raise SystemExit("STOCK_HANDOFF_KID do Ilya não consta em ILYA_HANDOFF_PUBLIC_KEYS.")
    if "PRIVATE" in estoque["ILYA_HANDOFF_PUBLIC_KEYS"]:
        raise SystemExit("O Estoque só pode receber a chave PÚBLICA do login único.")

    # Senhas novas, geradas aqui. Se roles.env já existe, reaproveita (idempotente).
    roles_path = env_dir / "roles.env"
    if roles_path.exists() and not args.force:
        roles = {}
        for line in roles_path.read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition("=")
            roles[key] = raw.strip("'")
        print("= roles.env: já existe, mantido")
    else:
        roles = {
            "ILYA_DB_SUPERUSER_PASSWORD": password(),
            "ESTOQUE_DB_SUPERUSER_PASSWORD": password(),
            "ILYA_APP_PASSWORD": password(),
            "ESTOQUE_APP_PASSWORD": password(),
            "ILYA_ESTOQUE_READONLY_PASSWORD": password(),
            "ILYA_REDIS_PASSWORD": password(),
            "ESTOQUE_REDIS_PASSWORD": password(),
        }
        write_env(roles_path, roles, True)

    ilya_api = dict(ilya)
    ilya_api.update(
        {
            "DATABASE_URL": f"postgresql+asyncpg://{ILYA_APP_ROLE}:{roles['ILYA_APP_PASSWORD']}@ilya-db:5432/{ILYA_DB}",
            "RATE_LIMIT_STORAGE_URI": f"redis://:{roles['ILYA_REDIS_PASSWORD']}@ilya-redis:6379/0",
            "FORWARDED_ALLOW_IPS": FORWARDED_ALLOW_IPS,
            "DEBUG": "false",
            # Travas fixas desta fase: e-mail desligado, Moloni e webhook fora.
            "ORDER_EMAIL_MODE": "off",
            "MOLONI_ENABLED": "false",
            "WEBHOOK_ENABLED": "false",
        }
    )
    ilya_worker = dict(ilya_email)
    ilya_worker.update(
        {
            "DATABASE_URL": ilya_api["DATABASE_URL"],
            "ORDER_EMAIL_MODE": "off",
            "MOLONI_ENABLED": "false",
            "WEBHOOK_ENABLED": "false",
        }
    )
    estoque_env = dict(estoque)
    estoque_env.update(
        {
            "DATABASE_URL": f"postgresql+asyncpg://{ESTOQUE_APP_ROLE}:{roles['ESTOQUE_APP_PASSWORD']}@estoque-db:5432/{ESTOQUE_DB}",
            "RATE_LIMIT_STORAGE_URI": f"redis://:{roles['ESTOQUE_REDIS_PASSWORD']}@estoque-redis:6379/0",
            "ILYA_READONLY_ENABLED": "true",
            "ILYA_READONLY_DATABASE_URL": f"postgresql+asyncpg://{ILYA_RO_ROLE}:{roles['ILYA_ESTOQUE_READONLY_PASSWORD']}@ilya-db:5432/{ILYA_DB}",
            "ILYA_CENTRAL_AUTH_ENABLED": "true",
            # Sync desligado até a virada. `sync-once` roda produtos e pedidos juntos.
            "ILYA_AUTO_SYNC_ENABLED": "false",
            "ILYA_AUTO_SYNC_ORDERS_ENABLED": "false",
            "ILYA_AUTO_SCOPE_DEACTIVATION_ENABLED": "false",
            "FORWARDED_ALLOW_IPS": FORWARDED_ALLOW_IPS,
            "DEBUG": "false",
        }
    )

    write_env(env_dir / "ilya-api.env", ilya_api, args.force)
    write_env(env_dir / "ilya-email.env", ilya_worker, args.force)
    write_env(env_dir / "estoque.env", estoque_env, args.force)
    write_env(
        env_dir / "ilya-db.env",
        {"POSTGRES_PASSWORD": roles["ILYA_DB_SUPERUSER_PASSWORD"], "POSTGRES_DB": ILYA_DB},
        args.force,
    )
    write_env(
        env_dir / "estoque-db.env",
        {"POSTGRES_PASSWORD": roles["ESTOQUE_DB_SUPERUSER_PASSWORD"], "POSTGRES_DB": ESTOQUE_DB},
        args.force,
    )
    write_env(env_dir / "ilya-redis.env", {"REDIS_PASSWORD": roles["ILYA_REDIS_PASSWORD"]}, args.force)
    write_env(
        env_dir / "estoque-redis.env", {"REDIS_PASSWORD": roles["ESTOQUE_REDIS_PASSWORD"]}, args.force
    )

    compose_env = args.out_root / ".env"
    if not compose_env.exists() or args.force:
        compose_env.write_text(
            f"ILYA_IMAGE={args.ilya_image}\n"
            f"ILYA_EMAIL_IMAGE={args.ilya_email_image}\n"
            f"ESTOQUE_IMAGE={args.estoque_image}\n",
            encoding="utf-8",
        )
        os.chmod(compose_env, 0o600)
        print("+ .env: tags das imagens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
