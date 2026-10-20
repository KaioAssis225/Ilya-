"""Builders mínimos de usuários e vínculos de mercado para testes de integração.

Não usa factory_boy. Cada builder recebe uma AsyncSession (da fixture de
teste), insere via ORM e chama flush() para que os IDs sejam gerados sem
fechar a transação de rollback.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.market import UserMarket, UserPlatformPermission


async def make_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    full_name: str = "Test User",
    role: UserRole = UserRole.admin,
    home_market: str = "BR",
    password: str = "TestPassword1",
) -> User:
    """Cria um User ativo com senha sintética e retorna a instância."""
    _email = email or f"test-{uuid.uuid4().hex[:8]}@ilya-test.invalid"
    user = User(
        email=_email,
        full_name=full_name,
        role=role,
        hashed_password=hash_password(password),
        is_active=True,
        home_market=home_market,
        auth_version=0,
    )
    db.add(user)
    await db.flush()
    return user


async def make_user_market(
    db: AsyncSession,
    user: User,
    *,
    market_code: str,
    role: str,
    status: str = "active",
    rep_id: uuid.UUID | None = None,
    linked_client_id: uuid.UUID | None = None,
) -> UserMarket:
    """Cria um UserMarket (vínculo usuário-mercado) e devolve a instância."""
    um = UserMarket(
        user_id=user.id,
        market_code=market_code,
        role=role,
        status=status,
        rep_id=rep_id,
        linked_client_id=linked_client_id,
    )
    db.add(um)
    await db.flush()
    return um


async def make_platform_permission(
    db: AsyncSession,
    user: User,
    *,
    capability: str = "platform_admin",
) -> UserPlatformPermission:
    """Cria permissão de plataforma para um usuário."""
    perm = UserPlatformPermission(
        user_id=user.id,
        capability=capability,
        is_active=True,
    )
    db.add(perm)
    await db.flush()
    return perm
