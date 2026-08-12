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
    if payload.get("ver") != user.auth_version:
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


# Papéis que decidem os termos comerciais do cliente: teto de desconto e
# carteira (`rep_id`). Cadastro (clients.create_client) e edição
# (sanitize_client_update_fields) leem esta mesma lista de propósito — já
# divergiram uma vez, e o efeito foi cliente com a carteira errada que ninguém
# conseguia corrigir pela API.
COMMERCIAL_ROLES = frozenset(
    {UserRole.admin, UserRole.cadastros, UserRole.produtos}
)


def sanitize_client_update_fields(update_data: dict, current_user: User) -> dict:
    """Remove de um PATCH de cliente os campos que o papel não pode alterar.

    O cliente-final nunca altera os próprios termos comerciais (SEC-PRICE-02).
    O representante pode escolher a tabela de preço do cliente da própria
    carteira, como permite o formulário, mas continua sem poder alterar o teto
    de desconto, o e-mail ou a atribuição da carteira.
    """
    if current_user.role == UserRole.representante:
        update_data.pop("email", None)
    # SEC-PRICE-02: conta de cliente-final (inclui legado
    # `vendedor`+linked_id) nunca define o próprio perfil de faturamento.
    if is_client_account(current_user):
        update_data.pop("price_profile", None)
    if current_user.role not in COMMERCIAL_ROLES:
        update_data.pop("max_discount", None)
        # Reatribuir carteira é decisão comercial: sem isso um representante
        # poderia puxar para si o cliente de outro — ou se livrar do próprio.
        update_data.pop("rep_id", None)
    return update_data


def _enforce_roles(current_user: User, allowed_roles: frozenset[UserRole]) -> User:
    if current_user.role == UserRole.admin:
        return current_user
    effective_role = (
        UserRole.cliente if is_client_account(current_user) else current_user.role
    )
    if effective_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação não permitida para o seu nível de acesso.",
        )
    return current_user


_DIRECTORY_ROLES = frozenset(
    {
        UserRole.vendedor,
        UserRole.representante,
        UserRole.cadastros,
        UserRole.produtos,
        UserRole.cliente,
    }
)

_ORDER_ROLES = frozenset(
    {
        UserRole.vendedor,
        UserRole.representante,
        UserRole.produtos,
        UserRole.cliente,
    }
)


def require_directory_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """Acesso aos diretórios comerciais; papéis novos são negados por padrão."""
    return _enforce_roles(current_user, _DIRECTORY_ROLES)


def require_order_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """Acesso a pedidos; o papel executivo permanece exclusivo do Dashboard."""
    return _enforce_roles(current_user, _ORDER_ROLES)


def require_dashboard_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """Bloco 95: acesso ao Dashboard BI. Role `executivo` sempre entra; qualquer
    outra role entra somente com a flag `can_view_dashboard` habilitada pelo
    admin (a flag não altera nenhuma outra permissão do usuário)."""
    if current_user.role == UserRole.admin:
        return current_user
    if current_user.role == UserRole.executivo or current_user.can_view_dashboard:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Operação não permitida para o seu nível de acesso.",
    )


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: User = Depends(get_current_user)):
        # SEC-01: contas legadas `vendedor`+linked_id são avaliadas como
        # `cliente`, nunca como operador interno.
        return _enforce_roles(current_user, frozenset(allowed_roles))
    return dependency
