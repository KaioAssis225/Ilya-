"""Regras do acesso ao Estoque Brasil (login único).

O Ilya é o porteiro: guarda só *se a pessoa pode* usar o Estoque
(`users.has_stock_access`). O papel dentro do Estoque é decidido lá.

Regras (todas no servidor, nunca no front):
- somente administrador da plataforma altera o campo;
- só vale para quem tem vínculo ativo no mercado BR;
- papéis `cliente` e `benchmark_readonly` nunca recebem o acesso.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.models.market import BR_MARKET
from app.models.user import User, UserRole

# Papéis que jamais entram no Estoque (pedido do Estoque, itens I-1 e I-2).
STOCK_BLOCKED_ROLES: frozenset[str] = frozenset({
    UserRole.cliente.value,
    UserRole.benchmark_readonly.value,
})


def _role_value(role: UserRole | str | None) -> str | None:
    return role.value if isinstance(role, UserRole) else role


def br_role_for_stock(user: User, links: Iterable | None = None) -> str | None:
    """Papel do vínculo BR ativo, ou None quando a pessoa não tem BR."""
    for link in (user.allowed_market_links if links is None else links):
        if (
            link.market_code == BR_MARKET
            and link.status == "active"
            and link.role is not None
        ):
            return _role_value(link.role)
    return None


def stock_access_denial(user: User, links: Iterable | None = None) -> str | None:
    """Motivo (interno) pelo qual a conta não pode ter acesso ao Estoque.

    `links` permite avaliar vínculos que ainda não foram gravados (edição de
    mercados no mesmo PATCH). Devolve None quando a conta é elegível.
    """
    all_links = list(user.allowed_market_links if links is None else links)
    if _role_value(user.role) in STOCK_BLOCKED_ROLES:
        return "role_blocked"
    if any(_role_value(link.role) in STOCK_BLOCKED_ROLES for link in all_links):
        return "role_blocked"
    if br_role_for_stock(user, all_links) is None:
        return "no_br_market"
    return None


def can_use_stock(user: User, links: Iterable | None = None) -> bool:
    """Elegibilidade atual: coluna marcada, conta ativa e regras acima."""
    return (
        bool(user.has_stock_access)
        and bool(user.is_active)
        and stock_access_denial(user, links) is None
    )
