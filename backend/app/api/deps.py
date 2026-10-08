import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.market import BR_MARKET, UserPlatformPermission
from app.core.security import decode_access_token
from app.core.markets import (
    MarketActor,
    MarketPrincipal,
    PlatformPrincipal,
    build_market_principal,
)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)


def _decode_token_payload(
    token: str,
    credentials_exception: HTTPException,
) -> dict:
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    return payload


async def _load_token_identity(
    payload: dict,
    db: AsyncSession,
    credentials_exception: HTTPException,
) -> User:
    """Valida identidade ativa e versão comum a todo access token."""
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise credentials_exception
    user = (await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )).scalar_one_or_none()
    if user is None or payload.get("ver") != user.auth_version:
        raise credentials_exception
    return user


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def get_market_principal(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db_session)
) -> MarketPrincipal:
    """Valida identidade e mercado e devolve o principal imutável da requisição."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decode_token_payload(token, credentials_exception)

    # Tokens anteriores a P2 não tinham claim scope e pertenciam ao fluxo
    # comercial. A tolerância é somente de leitura e termina com o TTL curto do
    # access token; tokens de plataforma sempre exigem scope explícito.
    if payload.get("scope", "market") != "market":
        raise credentials_exception

    user = await _load_token_identity(payload, db, credentials_exception)

    token_market = payload.get("market")
    if not isinstance(token_market, str):
        raise credentials_exception
    try:
        return await build_market_principal(db, user, token_market)
    except HTTPException:
        # Retirada de acesso invalida imediatamente o access token existente.
        raise credentials_exception


async def get_authenticated_user(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Identidade para operações da própria conta em ambos os escopos."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decode_token_payload(token, credentials_exception)
    user = await _load_token_identity(payload, db, credentials_exception)
    scope = payload.get("scope", "market")
    if scope == "market":
        market = payload.get("market")
        if not isinstance(market, str):
            raise credentials_exception
        try:
            await build_market_principal(db, user, market)
        except HTTPException:
            raise credentials_exception
    elif scope == "platform":
        capability = (await db.execute(select(UserPlatformPermission.user_id).where(
            UserPlatformPermission.user_id == user.id,
            UserPlatformPermission.is_active.is_(True),
        ).limit(1))).scalar_one_or_none()
        if capability is None:
            raise credentials_exception
    else:
        raise credentials_exception
    return user


async def get_current_principal(
    principal: MarketPrincipal = Depends(get_market_principal),
) -> MarketPrincipal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="must_change_password",
        )
    return principal


async def get_current_user(
    principal: MarketPrincipal = Depends(get_current_principal),
) -> MarketActor:
    """Ator comercial efetivo; papéis e vínculos vêm de user_markets."""
    return principal.actor


def require_br_fiscal_admin(
    principal: MarketPrincipal = Depends(get_current_principal),
) -> MarketPrincipal:
    """Autoriza mutações do IPI global somente a admin no mercado BR."""
    if principal.code != BR_MARKET or principal.actor.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A manutenção fiscal de IPI exige administrador no mercado BR.",
        )
    return principal


_EU_GROUP_EDITOR_ROLES = {UserRole.admin, UserRole.vendedor, UserRole.produtos}


def require_product_group_editor(
    principal: MarketPrincipal = Depends(get_current_principal),
) -> MarketPrincipal:
    """Quem pode criar/editar/excluir grupos de produto no mercado ativo.

    Brasil: o grupo carrega o IPI, então vale exatamente a guarda fiscal
    (`require_br_fiscal_admin`). Portugal: grupo EU não tem alíquota
    (eu_product_groups_r13_20261008) e segue os mesmos papéis que já editam
    os subgrupos EU (admin, vendedor, produtos).
    """
    if principal.code == BR_MARKET:
        return require_br_fiscal_admin(principal)
    if principal.actor.role not in _EU_GROUP_EDITOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para manter grupos neste mercado.",
        )
    return principal


async def get_platform_principal(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db_session),
) -> PlatformPrincipal:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais de plataforma inválidas ou expiradas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decode_token_payload(token, credentials_exception)
    if payload.get("scope") != "platform" or "market" in payload:
        raise credentials_exception
    user = await _load_token_identity(payload, db, credentials_exception)
    capabilities = frozenset((await db.execute(
        select(UserPlatformPermission.capability).where(
            UserPlatformPermission.user_id == user.id,
            UserPlatformPermission.is_active.is_(True),
        )
    )).scalars().all())
    if not capabilities:
        raise credentials_exception
    return PlatformPrincipal(user=user, capabilities=capabilities)


def require_platform_capability(capability: str):
    def dependency(
        principal: PlatformPrincipal = Depends(get_platform_principal),
    ) -> PlatformPrincipal:
        if not principal.has(capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Capacidade de plataforma não concedida.",
            )
        return principal
    return dependency


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


# Decisões comerciais distintas têm matrizes próprias. O papel `produtos` pode
# manter a carteira cadastral do cliente, mas não define seu teto de desconto.
# Cadastro e edição leem estas mesmas listas para não abrirem uma rota
# alternativa com mais privilégio.
CLIENT_ASSIGNMENT_ROLES = frozenset(
    {UserRole.admin, UserRole.cadastros, UserRole.produtos}
)
DISCOUNT_MANAGEMENT_ROLES = frozenset(
    {UserRole.admin, UserRole.cadastros}
)
CLIENT_IDENTITY_MANAGEMENT_ROLES = frozenset(
    {UserRole.admin, UserRole.cadastros}
)


def sanitize_client_update_fields(update_data: dict, current_user: User) -> dict:
    """Remove de um PATCH de cliente os campos que o papel não pode alterar.

    O cliente-final nunca altera os próprios termos comerciais (SEC-PRICE-02).
    O representante pode escolher a tabela de preço do cliente da própria
    carteira, como permite o formulário, mas continua sem poder alterar o teto
    de desconto, a identidade cadastral ou a atribuição da carteira. E-mail de
    referência e identificadores fiscais são corrigidos por atendimento
    (`admin`/`cadastros`); o titular precisa passar por reverificação fora deste
    PATCH comum.
    """
    if current_user.role not in CLIENT_IDENTITY_MANAGEMENT_ROLES:
        for field in ("email", "cpf_cnpj", "tax_id"):
            update_data.pop(field, None)
    # SEC-PRICE-02: conta de cliente-final (inclui legado
    # `vendedor`+linked_id) nunca define o próprio perfil de faturamento.
    if is_client_account(current_user):
        update_data.pop("price_profile", None)
    if current_user.role not in DISCOUNT_MANAGEMENT_ROLES:
        update_data.pop("max_discount", None)
    if current_user.role not in CLIENT_ASSIGNMENT_ROLES:
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
