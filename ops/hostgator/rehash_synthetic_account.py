"""Refaz o hash da senha da conta SINTÉTICA de homologação com o pepper de produção.

Por quê: o hash copiado do banco de homologação foi gerado com o PASSWORD_PEPPER
da homologação. Esta stack usa o pepper de produção (preservado de propósito:
sem ele ninguém loga), então a conta sintética não entra até o hash ser refeito.
As contas reais não são afetadas: elas já foram feitas com o pepper de produção.

Roda DENTRO do container da API (ver RUNBOOK-virada.md), com o arquivo de
credenciais montado somente-leitura. Não imprime a senha nem o hash.

  docker compose run --rm --no-deps \
    -v /opt/ilya-production/rehash_synthetic_account.py:/tmp/rehash.py:ro \
    -v /opt/ilya-acceptance/acceptance.env:/tmp/cred.env:ro \
    ilya-api python /tmp/rehash.py /tmp/cred.env
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def read(path: str) -> tuple[str, str]:
    values = {}
    for line in open(path, encoding="utf-8"):
        key, _, raw = line.rstrip("\n").partition("=")
        if key in ("ADMIN_EMAIL", "ADMIN_PASSWORD"):
            values[key] = raw.strip().strip("'\"")
    return values["ADMIN_EMAIL"], values["ADMIN_PASSWORD"]


async def main(path: str) -> None:
    email, password = read(path)
    # Trava: só mexe em conta sintética (domínio reservado example.com).
    if not email.endswith("@ilya.example.com"):
        raise SystemExit("Recusado: a conta não é sintética (@ilya.example.com).")
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            raise SystemExit("Conta sintética não encontrada.")
        user.hashed_password = hash_password(password)
        await db.commit()
    print("hash da conta sintética refeito com o pepper de produção.")


asyncio.run(main(sys.argv[1]))
