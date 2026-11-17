"""Transferência de peças do Estoque EU para outra box.

Orçamento não é destino daqui: a peça só chega a um orçamento pela aba Novo
orçamento (``showroom_source_item_id``), nunca a um orçamento já existente."""

import uuid
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.api.routers.showrooms import _MANAGER, _get_box, _read_box
from app.core.markets import MarketPrincipal
from app.models.market import PriceList, ProductMarket, ProductPrice
from app.models.product import Product
from app.models.showroom import ShowroomBox, ShowroomBoxItem, ShowroomTransfer
from app.models.user import User
from app.schemas.showroom import (
    ShowroomTransferCreate,
    ShowroomTransferRead,
    ShowroomTransferResult,
)


router = APIRouter(prefix="/api/v1/showroom-boxes", tags=["showroom-boxes"])

MAX_QUANTITY = 1_000_000


async def _lock_boxes(db: AsyncSession, source_id: uuid.UUID, destination_id: uuid.UUID):
    """Trava as boxes envolvidas em ordem fixa de id: duas transferências
    cruzadas (A para B e B para A) esperam uma pela outra em vez de travar em deadlock."""
    wanted = {source_id, destination_id}
    rows = (await db.execute(
        select(ShowroomBox)
        .where(ShowroomBox.id.in_(wanted), ShowroomBox.market_code == "EU")
        .order_by(ShowroomBox.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()
    by_id = {row.id: row for row in rows}
    if source_id not in by_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Armazém não encontrado.")
    if destination_id not in by_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Armazém de destino não encontrado.")
    return by_id[source_id], by_id[destination_id]


async def _ensure_priced_in_box(db: AsyncSession, product_id: uuid.UUID, box: ShowroomBox) -> None:
    found = (await db.execute(
        select(Product.id)
        .join(ProductMarket, ProductMarket.product_id == Product.id)
        .join(PriceList, (PriceList.market_code == "EU") & (PriceList.code == box.price_list_code)
              & (PriceList.is_active.is_(True)))
        .join(ProductPrice, (ProductPrice.product_id == Product.id) & (ProductPrice.price_list_id == PriceList.id))
        .where(
            Product.id == product_id, Product.market_code == "EU", Product.is_active.is_(True),
            ProductMarket.market_code == "EU", ProductMarket.is_available.is_(True),
        )
        .execution_options(skip_market_scope=True)
    )).scalar_one_or_none()
    if found is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"O produto não está disponível ou não tem preço na tabela do armazém '{box.name}'.",
        )


def _transfer_read(row: ShowroomTransfer) -> ShowroomTransferRead:
    return ShowroomTransferRead(
        id=row.id, created_at=row.created_at, created_by_name=row.created_by_name,
        source_box_id=row.source_box_id, source_box_name=row.source_box_name,
        destination_type=row.destination_type,
        destination_box_id=row.destination_box_id, destination_box_name=row.destination_box_name,
        destination_order_id=row.destination_order_id,
        destination_order_code=row.destination_order_code,
        product_code=row.product_code, quantity=row.quantity,
        optional_choices=row.optional_configuration,
    )


@router.post(
    "/{box_id}/transfers", response_model=ShowroomTransferResult,
    status_code=status.HTTP_201_CREATED,
)
async def transfer_item(
    box_id: uuid.UUID,
    payload: ShowroomTransferCreate,
    language: Literal["pt-PT", "en-GB"] = Query(default="pt-PT"),
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
    current_user: User = Depends(get_current_user),
):
    """Tira ``quantity`` peças de um item da box e as leva para OUTRA BOX, numa
    única transação. Não existe destino "orçamento" nesta rota (``type`` diferente
    de ``box`` é recusado com 422): a peça só vai para um orçamento pela aba Novo
    orçamento, e nunca para um orçamento já existente.

    As boxes e a linha de origem ficam travadas até o commit: duas
    transferências simultâneas do mesmo item se enfileiram e a segunda enxerga
    o saldo já reduzido. O saldo nunca fica negativo.
    """
    destination_box_id = payload.destination.box_id
    if destination_box_id == box_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Escolha um armazém de destino diferente da origem.")
    try:
        return await _transfer_item(db, box_id, destination_box_id, payload, language, current_user)
    except HTTPException:
        await db.rollback()
        raise


async def _transfer_item(
    db: AsyncSession,
    box_id: uuid.UUID,
    destination_box_id: uuid.UUID,
    payload: ShowroomTransferCreate,
    language: Literal["pt-PT", "en-GB"],
    current_user: User,
) -> ShowroomTransferResult:
    source, target = await _lock_boxes(db, box_id, destination_box_id)
    item = (await db.execute(
        select(ShowroomBoxItem)
        .where(ShowroomBoxItem.id == payload.item_id, ShowroomBoxItem.box_id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produto não encontrado neste armazém.")
    if payload.quantity > item.quantity:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Quantidade maior que o saldo do armazém: há {item.quantity} peça(s).",
        )
    product = (await db.execute(
        select(Product).where(Product.id == item.product_id).execution_options(skip_market_scope=True)
    )).scalar_one()
    configuration = list(item.optional_configuration)

    await _ensure_priced_in_box(db, item.product_id, target)
    merged = (await db.execute(
        pg_insert(ShowroomBoxItem)
        .values(
            box_id=target.id, product_id=item.product_id, quantity=payload.quantity,
            optional_configuration=configuration, configuration_key=item.configuration_key,
        )
        .on_conflict_do_update(
            constraint="uq_showroom_box_items_configuration",
            set_={"quantity": ShowroomBoxItem.quantity + payload.quantity, "updated_at": func.now()},
            where=ShowroomBoxItem.quantity + payload.quantity <= MAX_QUANTITY,
        )
        .returning(ShowroomBoxItem.id)
    )).scalar_one_or_none()
    if merged is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A quantidade máxima por produto no armazém de destino é 1.000.000.",
        )

    # Saída da origem (mesma transação do destino).
    if payload.quantity == item.quantity:
        await db.delete(item)
    else:
        item.quantity -= payload.quantity
    transfer = ShowroomTransfer(
        market_code="EU",
        created_by_user_id=current_user.id,
        created_by_name=current_user.full_name,
        source_box_id=source.id,
        source_box_name=source.name,
        destination_type="box",
        destination_box_id=target.id,
        destination_box_name=target.name,
        product_id=product.id,
        product_code=product.product_code,
        quantity=payload.quantity,
        optional_configuration=configuration,
    )
    db.add(transfer)
    await db.flush()
    await db.commit()

    await db.refresh(source)
    return ShowroomTransferResult(
        transfer=_transfer_read(transfer),
        box=await _read_box(db, source, language),
    )


@router.get("/{box_id}/transfers", response_model=List[ShowroomTransferRead])
async def list_transfers(
    box_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    principal: MarketPrincipal = _MANAGER,
):
    box = await _get_box(db, box_id)
    rows = (await db.execute(
        select(ShowroomTransfer)
        .where(or_(ShowroomTransfer.source_box_id == box.id, ShowroomTransfer.destination_box_id == box.id))
        .order_by(ShowroomTransfer.created_at.desc(), ShowroomTransfer.id)
        .limit(100)
    )).scalars().all()
    return [_transfer_read(row) for row in rows]
