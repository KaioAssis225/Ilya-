"""
Cria o usuário admin inicial.
Uso: docker compose exec backend python seed_admin.py

Variáveis de ambiente obrigatórias (sem fallback):
  ADMIN_EMAIL     e-mail do admin
  ADMIN_PASSWORD  senha inicial (troque após o primeiro login)
  ADMIN_NAME      nome completo (opcional, padrão: Administrador)
"""
import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.core.security import hash_password


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"ERRO: variável de ambiente '{name}' não definida.")
        print("Defina ADMIN_EMAIL e ADMIN_PASSWORD antes de executar este script.")
        sys.exit(1)
    return value


ADMIN_EMAIL = _require_env("ADMIN_EMAIL")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrador")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == ADMIN_EMAIL))).scalar_one_or_none()
        if existing:
            print(f"Usuário '{ADMIN_EMAIL}' já existe. Nenhuma ação necessária.")
            return

        admin = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name=ADMIN_NAME,
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Admin criado: {ADMIN_EMAIL}")
        print("ATENÇÃO: Altere a senha após o primeiro login!")


if __name__ == "__main__":
    asyncio.run(main())
