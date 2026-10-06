"""
Cria o usuário admin inicial.
Uso: docker compose exec backend python seed_admin.py

Variáveis de ambiente obrigatórias (sem fallback):
  ADMIN_EMAIL     e-mail do admin
  ADMIN_PASSWORD  senha inicial (troque após o primeiro login)
  ADMIN_NAME      nome completo (opcional, padrão: Administrador)

Na ausência de outro administrador ativo da plataforma, o e-mail configurado
recebe `platform_admin`. Se a conta já existir, senha, papel e vínculos
comerciais são preservados; reinícios posteriores não refazem grants revogados.
"""
import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import AsyncSessionLocal
from app.core.platform import lock_platform_admin_guard
from app.models.market import UserMarket, UserPlatformPermission
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
        existing = (
            await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing:
            admin = existing
            print(f"Usuário '{ADMIN_EMAIL}' já existe; identidade preservada.")
        else:
            admin = User(
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                full_name=ADMIN_NAME,
                role=UserRole.admin,
                is_active=True,
                home_market="BR",
            )
            db.add(admin)
            await db.flush()
            db.add(UserMarket(
                user_id=admin.id,
                market_code="BR",
                role=UserRole.admin.value,
                status="active",
                can_view_dashboard=False,
                can_approve_tax=False,
            ))

        await lock_platform_admin_guard(db)
        active_platform_admin = (
            await db.execute(
                select(UserPlatformPermission.user_id)
                .join(User, User.id == UserPlatformPermission.user_id)
                .where(
                    UserPlatformPermission.capability == "platform_admin",
                    UserPlatformPermission.is_active.is_(True),
                    User.is_active.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if active_platform_admin is None:
            if not admin.is_active:
                raise RuntimeError(
                    f"ADMIN_EMAIL '{ADMIN_EMAIL}' está inativo e não pode "
                    "ser o administrador inicial da plataforma."
                )
            permission = await db.get(
                UserPlatformPermission,
                (admin.id, "platform_admin"),
            )
            if permission is None:
                db.add(UserPlatformPermission(
                    user_id=admin.id,
                    capability="platform_admin",
                    is_active=True,
                ))
            else:
                permission.is_active = True

        await db.commit()
        if active_platform_admin is not None:
            print("Administrador da plataforma já provisionado; grants preservados.")
        elif existing:
            print(f"Permissão de administrador da plataforma ativa: {ADMIN_EMAIL}")
        else:
            print(f"Admin criado: {ADMIN_EMAIL}")
            print("ATENÇÃO: Altere a senha após o primeiro login!")


if __name__ == "__main__":
    asyncio.run(main())
