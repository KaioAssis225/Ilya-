"""Permissões de catálogo por representante e cliente (catalog_permissions_r21).

Fonte única da regra do planejamento "Orçamentos, Catálogos e Permissões
Comerciais" v1.2.0. Listagem de produtos, cadastro de clientes/representantes e
pedidos chamam estas funções; o frontend só espelha o resultado.

Um escopo é `None` (todos os catálogos do mercado, inclusive os criados depois)
ou o conjunto de ids permitidos. Conjunto vazio significa nenhum catálogo.
"""
import uuid
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import is_client_account
from app.models.catalog import Catalog, ClientCatalog, RepresentativeCatalog
from app.models.client import Client
from app.models.representative import Representative
from app.models.user import User, UserRole

CatalogScope = frozenset[uuid.UUID] | None


def owner_scope(owner: Client | Representative) -> CatalogScope:
    return None if owner.all_catalogs else frozenset(owner.catalog_ids)


def intersect(*scopes: CatalogScope) -> CatalogScope:
    result: CatalogScope = None
    for scope in scopes:
        if scope is None:
            continue
        result = scope if result is None else result & scope
    return result


def allows(scope: CatalogScope, catalog_id: uuid.UUID) -> bool:
    return scope is None or catalog_id in scope


async def visible_catalog_scope(
    db: AsyncSession, user: User, market_code: str
) -> CatalogScope:
    """Catálogos que o usuário enxerga fora de um pedido (DEC-08).

    Representante vê os próprios; conta de cliente, os do cadastro (DEC-03).
    Papéis internos veem tudo. Registro ausente não vira acesso total.
    """
    if user.role == UserRole.representante:
        if user.rep_id is None:
            return frozenset()
        rep = (await db.execute(select(Representative).where(
            Representative.id == user.rep_id,
            Representative.market_code == market_code,
        ))).scalar_one_or_none()
        return owner_scope(rep) if rep else frozenset()
    if is_client_account(user):
        if user.linked_id is None:
            return frozenset()
        client = (await db.execute(select(Client).where(
            Client.id == user.linked_id,
            Client.market_code == market_code,
        ))).scalar_one_or_none()
        return owner_scope(client) if client else frozenset()
    return None


def order_catalog_scope(
    user: User, client: Client, rep: Representative | None
) -> CatalogScope:
    """Catálogos que um pedido deste cliente pode ter.

    Conta de cliente: só o cadastro do cliente (DEC-03). Demais papéis: cliente
    ∩ representante do pedido, quando houver (DEC-05). O representante logado é
    sempre o representante do pedido, então cai na mesma regra.
    """
    if is_client_account(user):
        return owner_scope(client)
    return intersect(owner_scope(client), owner_scope(rep) if rep else None)


async def resolve_catalog_selection(
    db: AsyncSession,
    market_code: str,
    *,
    all_catalogs: bool | None,
    catalog_ids: Iterable[uuid.UUID] | None,
    limit: CatalogScope = None,
) -> tuple[bool, frozenset[uuid.UUID]] | None:
    """Valida o que um formulário pediu para `all_catalogs`/`catalog_ids`.

    Retorna `None` quando nada foi informado. Mandar só `catalog_ids` implica
    seleção específica. `limit` é o teto de quem está editando (DEC-04): um
    representante restrito não concede "todos" nem catálogo que não vende.
    """
    if all_catalogs is None and catalog_ids is None:
        return None
    if all_catalogs is None:
        all_catalogs = False
    if all_catalogs:
        if limit is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não pode liberar todos os catálogos.",
            )
        return True, frozenset()
    ids = frozenset(catalog_ids or ())
    if not ids:
        raise HTTPException(
            status_code=422,
            detail="Selecione ao menos um catálogo ou libere todos.",
        )
    found = set((await db.execute(select(Catalog.id).where(
        Catalog.market_code == market_code,
        Catalog.id.in_(ids),
    ))).scalars().all())
    if found != ids:
        raise HTTPException(
            status_code=422,
            detail="Um ou mais catálogos não pertencem ao mercado ativo.",
        )
    if limit is not None and not ids <= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode liberar catálogos que você mesmo vende.",
        )
    return False, ids


def apply_catalog_selection(
    owner: Client | Representative,
    selection: tuple[bool, frozenset[uuid.UUID]],
) -> None:
    """Grava a seleção pela diferença: recriar um vínculo com a mesma chave
    no mesmo flush colidiria na chave primária."""
    all_catalogs, ids = selection
    owner.all_catalogs = all_catalogs
    link_cls = ClientCatalog if isinstance(owner, Client) else RepresentativeCatalog
    owner.catalog_links[:] = [
        link for link in owner.catalog_links if link.catalog_id in ids
    ]
    current = {link.catalog_id for link in owner.catalog_links}
    for catalog_id in sorted(ids - current):
        owner.catalog_links.append(
            link_cls(catalog_id=catalog_id, market_code=owner.market_code)
        )
