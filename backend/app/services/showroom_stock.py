"""Baixa do Estoque EU ao salvar um orçamento novo vindo da Transferência.

A tela "Novo orçamento" recebe a peça do estoque sem tirar nada da box. Só
quando o orçamento é salvo o servidor baixa a quantidade, na mesma transação
que cria o orçamento: se o saldo não cobre, o orçamento não é criado.
"""

import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.markets import MarketPrincipal
from app.models.order import Order, OrderItem
from app.models.showroom import ShowroomBox, ShowroomBoxItem, ShowroomTransfer
from app.models.user import User
from app.schemas.order import OrderItemCreate


def reject_showroom_references(items: list[OrderItemCreate], reason: str) -> None:
    """Edição, cópia e revisão não baixam estoque: só o orçamento novo."""
    if any(item.showroom_source_item_id is not None for item in items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, reason)


async def take_stock_for_order(
    db: AsyncSession,
    *,
    principal: MarketPrincipal,
    current_user: User,
    order: Order,
    lines: list[tuple[OrderItemCreate, OrderItem]],
) -> None:
    """Dá baixa nas linhas que vieram do estoque e registra a transferência.

    Valida tudo antes de mexer em qualquer saldo; trava boxes (ordem fixa de id)
    e linhas até o commit do orçamento, como a transferência direta faz.
    """
    if not lines:
        return
    if (
        principal.code != "EU"
        or principal.access is None
        or not principal.actor.can_manage_showrooms
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Sem acesso ao Estoque para dar baixa nesta peça.",
        )
    wanted_ids = {item_in.showroom_source_item_id for item_in, _ in lines}
    first_pass = (await db.execute(
        select(ShowroomBoxItem.id, ShowroomBoxItem.box_id).where(ShowroomBoxItem.id.in_(wanted_ids))
    )).all()
    box_ids = sorted({row.box_id for row in first_pass})
    boxes = {row.id: row for row in (await db.execute(
        select(ShowroomBox)
        .where(ShowroomBox.id.in_(box_ids), ShowroomBox.market_code == "EU")
        .order_by(ShowroomBox.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()} if box_ids else {}
    stock = {row.id: row for row in (await db.execute(
        select(ShowroomBoxItem)
        .where(ShowroomBoxItem.id.in_(wanted_ids), ShowroomBoxItem.box_id.in_(list(boxes)))
        .order_by(ShowroomBoxItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalars().all()} if boxes else {}

    requested: dict[uuid.UUID, int] = defaultdict(int)
    for item_in, order_item in lines:
        item = stock.get(item_in.showroom_source_item_id)
        if item is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A peça {item_in.product_code} não está mais no estoque "
                "(foi transferida ou removida). Remova-a do orçamento.",
            )
        if order_item.sold_by_area or order_item.is_special:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{item_in.product_code}: item de estoque não pode ser tapete por área nem especial.",
            )
        quantity = Decimal(order_item.qty)
        if quantity != quantity.to_integral_value() or quantity < 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{item_in.product_code}: a quantidade vinda do estoque deve ser inteira.",
            )
        if item.product.product_code != order_item.product_code:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A linha {order_item.product_code} não corresponde à peça do estoque.",
            )
        requested[item.id] += int(quantity)

    for item_id, quantity in requested.items():
        item = stock[item_id]
        if quantity > item.quantity:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Saldo insuficiente na box '{boxes[item.box_id].name}' para "
                f"{item.product.product_code}: o orçamento pede {quantity} e há {item.quantity}.",
            )

    for item_in, order_item in lines:
        item = stock[item_in.showroom_source_item_id]
        quantity = int(Decimal(order_item.qty))
        db.add(ShowroomTransfer(
            market_code="EU",
            created_by_user_id=current_user.id,
            created_by_name=current_user.full_name,
            source_box_id=item.box_id,
            source_box_name=boxes[item.box_id].name,
            destination_type="order",
            destination_order_id=order.id,
            destination_order_code=order.code,
            product_id=item.product_id,
            product_code=order_item.product_code,
            quantity=quantity,
            optional_configuration=list(item.optional_configuration),
        ))
    for item_id, quantity in requested.items():
        item = stock[item_id]
        if quantity == item.quantity:
            await db.delete(item)
        else:
            item.quantity -= quantity
