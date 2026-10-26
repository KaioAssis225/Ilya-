"""Permissões de tabela de preço por representante e cliente (price_list_access_r23).

Um escopo é `None` (todas as tabelas do mercado, inclusive as criadas depois)
ou o conjunto de códigos permitidos. O perfil de faturamento do cliente sempre
entra no escopo, além das tabelas escolhidas no cadastro.
"""
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import is_client_account
from app.models.client import Client
from app.models.market import PriceList
from app.models.representative import Representative
from app.models.user import User, UserRole

PriceScope = frozenset[str] | None
PRICE_LIST_ORDER = ("lojista", "corporativo", "pvp", "arquiteto")


def owner_price_scope(owner: Client | Representative) -> PriceScope:
    if owner.all_price_lists:
        return None
    codes = set(owner.price_list_codes)
    if isinstance(owner, Client):
        codes.add(owner.price_profile)
    return frozenset(codes)


def allows_price(scope: PriceScope, code: str) -> bool:
    return scope is None or code in scope


async def visible_price_scope(
    db: AsyncSession, user: User, market_code: str
) -> PriceScope:
    """Tabelas de preço que o usuário enxerga fora de um pedido.

    Representante vê as do próprio cadastro; conta de cliente vê as do cadastro
    mais o perfil de faturamento. Papéis internos veem tudo. Registro ausente
    não vira acesso total.
    """
    if user.role == UserRole.representante:
        if user.rep_id is None:
            return frozenset()
        rep = (await db.execute(select(Representative).where(
            Representative.id == user.rep_id,
            Representative.market_code == market_code,
        ))).scalar_one_or_none()
        return owner_price_scope(rep) if rep else frozenset()
    if is_client_account(user):
        if user.linked_id is None:
            return frozenset({"lojista"})
        client = (await db.execute(select(Client).where(
            Client.id == user.linked_id,
            Client.market_code == market_code,
        ))).scalar_one_or_none()
        return owner_price_scope(client) if client else frozenset({"lojista"})
    return None


async def resolve_price_selection(
    db: AsyncSession,
    market_code: str,
    *,
    all_price_lists: bool | None,
    price_list_codes: Iterable[str] | None,
    limit: PriceScope = None,
    allow_empty: bool = False,
) -> tuple[bool, tuple[str, ...]] | None:
    """Valida o que um formulário pediu para `all_price_lists`/`price_list_codes`.

    Retorna `None` quando nada foi informado. Mandar só `price_list_codes`
    implica seleção específica. `limit` é o teto de quem está editando: um
    representante restrito não concede "todas" nem tabela que não vê.
    """
    if all_price_lists is None and price_list_codes is None:
        return None
    if all_price_lists is None:
        all_price_lists = False
    if all_price_lists:
        if limit is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não pode liberar todas as tabelas de preço.",
            )
        return True, ()
    selected = set(price_list_codes or ())
    codes = tuple(code for code in PRICE_LIST_ORDER if code in selected)
    if not codes:
        if not allow_empty:
            raise HTTPException(
                status_code=422,
                detail="Selecione ao menos uma tabela de preço ou libere todas.",
            )
        return False, ()
    if limit is not None and not set(codes) <= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode liberar tabelas de preço que você mesmo vê.",
        )
    found = set((await db.execute(select(PriceList.code).where(
        PriceList.market_code == market_code,
        PriceList.is_active.is_(True),
        PriceList.code.in_(codes),
    ))).scalars().all())
    if found != set(codes):
        raise HTTPException(
            status_code=422,
            detail="Uma ou mais tabelas de preço não existem no mercado ativo.",
        )
    return False, codes


def apply_price_selection(
    owner: Client | Representative,
    selection: tuple[bool, tuple[str, ...]],
) -> None:
    owner.all_price_lists, owner.price_list_codes = selection[0], list(selection[1])


def ensure_price_visible(scope: PriceScope, code: str) -> None:
    if not allows_price(scope, code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Este cliente usa a tabela de preço {code}, que você não pode ver.",
        )
