import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User, UserRole
from app.core.security import decode_access_token

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def get_authenticated_user(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """Validates token and returns the user. Does NOT enforce must_change_password."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_user(
    user: User = Depends(get_authenticated_user),
) -> User:
    """Returns the current user, raising 403 if a password change is required."""
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="must_change_password",
        )
    return user


def is_client_account(user: User) -> bool:
    """Conta de portal do cliente-final (SEC-01).

    A role oficial é `cliente`; contas legadas criadas antes da migração 0028
    ainda podem ter `vendedor` + `linked_id` — tratadas aqui como cliente para
    que nunca exerçam permissão de operador interno mesmo antes de migrar.
    """
    return user.role == UserRole.cliente or (
        user.role == UserRole.vendedor and user.linked_id is not None
    )


def is_internal_operator(user: User) -> bool:
    """Operador interno de vendas: `vendedor` sem vínculo de cliente (SEC-01)."""
    return user.role == UserRole.vendedor and user.linked_id is None


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role == UserRole.admin:
            return current_user
        # SEC-01: uma conta de cliente-final nunca deve receber permissão de
        # operador interno. Se estiver com a role legada `vendedor`+linked_id,
        # rebaixamos para `cliente` na verificação — assim endpoints que aceitam
        # `vendedor` (ex.: catálogo) a rejeitam até a migração 0028 concluir.
        effective_role = UserRole.cliente if is_client_account(current_user) else current_user.role
        if effective_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operação não permitida para o seu nível de acesso."
            )
        return current_user
    return dependency
