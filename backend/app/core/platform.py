from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Serializa mudanças capazes de remover o último administrador da plataforma.
# O lock é transacional e compartilhado entre exclusão, suspensão e grants.
_PLATFORM_ADMIN_GUARD_LOCK = 730_210_001


async def lock_platform_admin_guard(db: AsyncSession) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": _PLATFORM_ADMIN_GUARD_LOCK},
    )
