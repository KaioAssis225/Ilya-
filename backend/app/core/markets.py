from dataclasses import dataclass

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


@dataclass(frozen=True)
class MarketPrincipal:
    """Identidade autenticada e mercado autorizado de uma requisição.

    O código de mercado não é inferido: ele já foi validado contra o token e os
    vínculos do usuário antes da construção deste objeto.
    """

    user: User
    market: MarketContext

    @property
    def code(self) -> str:
        return self.market.code

    def bind(self, db: AsyncSession) -> None:
        """Vincula à sessão ORM exatamente o mercado validado no principal."""
        db.sync_session.info["active_market"] = self.code


MARKETS = {
    BR_MARKET: MarketContext(BR_MARKET, "BRL", "pt-BR", "IPI"),
    EU_MARKET: MarketContext(EU_MARKET, "EUR", "pt-PT", "IVA"),
}


def market_is_enabled(code: str) -> bool:
    return code == BR_MARKET or (code == EU_MARKET and settings.EUROPE_MARKET_ENABLED)


async def allowed_markets(db: AsyncSession, user: User) -> list[str]:
    if user.role == UserRole.admin:
        codes = [BR_MARKET, EU_MARKET]
    else:
        codes = list((await db.execute(
            select(UserMarket.market_code)
            .where(UserMarket.user_id == user.id)
            .order_by(UserMarket.market_code)
        )).scalars().all())
        if user.home_market not in codes:
            codes.append(user.home_market)
    candidates = [code for code in codes if market_is_enabled(code)]
    enabled = set((await db.execute(
        select(Market.code).where(Market.code.in_(candidates), Market.is_enabled.is_(True))
    )).scalars().all())
    return [code for code in candidates if code in enabled]


async def require_allowed_market(db: AsyncSession, user: User, code: str) -> str:
    normalized = code.upper()
    if normalized not in MARKETS or normalized not in await allowed_markets(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Mercado não autorizado para esta conta.")
    return normalized


async def build_market_principal(
    db: AsyncSession,
    user: User,
    token_market: str,
) -> MarketPrincipal:
    code = await require_allowed_market(db, user, token_market)
    principal = MarketPrincipal(user=user, market=MARKETS[code])
    principal.bind(db)
    return principal
