from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.market import BR_MARKET, EU_MARKET, Market, UserMarket
from app.models.user import User, UserRole


@dataclass(frozen=True)
class MarketContext:
    code: str
    currency: str
    locale: str
    tax_label: str


class MarketActor:
    """Visão comercial da identidade no mercado ativo, sem mutar o ORM."""

    __slots__ = ("identity", "access")

    def __init__(self, identity: User, access: UserMarket) -> None:
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "access", access)

    @property
    def role(self) -> UserRole:
        if self.access.role is None:
            raise RuntimeError("Vínculo ativo sem papel comercial.")
        return UserRole(self.access.role)

    @property
    def linked_id(self):
        return self.access.linked_client_id

    @property
    def rep_id(self):
        return self.access.rep_id

    @property
    def can_view_dashboard(self) -> bool:
        return self.access.can_view_dashboard

    @property
    def can_approve_tax(self) -> bool:
        return self.access.can_approve_tax

    def __getattr__(self, name: str) -> Any:
        return getattr(self.identity, name)


@dataclass(frozen=True)
class MarketPrincipal:
    """Identidade, vínculo comercial e mercado validados da requisição."""

    user: User
    market: MarketContext
    access: UserMarket | None = None

    @property
    def code(self) -> str:
        return self.market.code

    @property
    def actor(self) -> MarketActor:
        if self.access is None:
            raise RuntimeError("Principal de mercado sem vínculo validado.")
        return MarketActor(self.user, self.access)

    def bind(self, db: AsyncSession) -> None:
        db.sync_session.info["active_market"] = self.code


@dataclass(frozen=True)
class PlatformPrincipal:
    """Sessão administrativa da plataforma, sem mercado comercial ativo."""

    user: User
    capabilities: frozenset[str]

    def has(self, capability: str) -> bool:
        return "platform_admin" in self.capabilities or capability in self.capabilities


MARKETS = {
    BR_MARKET: MarketContext(BR_MARKET, "BRL", "pt-BR", "IPI"),
    EU_MARKET: MarketContext(EU_MARKET, "EUR", "pt-PT", "IVA"),
}


def market_is_enabled(code: str) -> bool:
    return code == BR_MARKET or (code == EU_MARKET and settings.EUROPE_MARKET_ENABLED)


async def allowed_market_accesses(db: AsyncSession, user: User) -> list[UserMarket]:
    """Somente vínculos ativos em mercados habilitados concedem acesso."""
    rows = list((await db.execute(
        select(UserMarket)
        .join(Market, Market.code == UserMarket.market_code)
        .where(
            UserMarket.user_id == user.id,
            UserMarket.status == "active",
            UserMarket.role.is_not(None),
            Market.is_enabled.is_(True),
        )
        .order_by(UserMarket.market_code)
    )).scalars().all())
    return [row for row in rows if market_is_enabled(row.market_code)]


async def allowed_markets(db: AsyncSession, user: User) -> list[str]:
    return [link.market_code for link in await allowed_market_accesses(db, user)]


async def require_market_access(db: AsyncSession, user: User, code: str) -> UserMarket:
    normalized = code.upper()
    if normalized not in MARKETS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Mercado não autorizado para esta conta.")
    for access in await allowed_market_accesses(db, user):
        if access.market_code == normalized:
            return access
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Mercado não autorizado para esta conta.")


async def require_allowed_market(db: AsyncSession, user: User, code: str) -> str:
    return (await require_market_access(db, user, code)).market_code


async def build_market_principal(
    db: AsyncSession, user: User, token_market: str
) -> MarketPrincipal:
    access = await require_market_access(db, user, token_market)
    principal = MarketPrincipal(user=user, market=MARKETS[access.market_code], access=access)
    principal.bind(db)
    return principal
