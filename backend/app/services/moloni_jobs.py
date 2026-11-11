"""Fila transacional de exportação de pedidos EU para o Moloni."""
import logging
import uuid
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.moloni import MoloniExportJob
from app.models.order import OrderItem
from app.models.product import PROTOTYPE_CODE_PREFIX

logger = logging.getLogger("ilya.moloni_jobs")

async def enqueue_finalized_eu_order(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Idempotente: finalizar duas vezes nunca pode gerar dois documentos."""
    if settings.MOLONI_BLOCKED:
        return
    # Protótipo nunca vai ao Moloni: não existe no catálogo nem é faturado.
    if await order_has_prototype_items(db, order_id):
        logger.info("Pedido com protótipo não vai ao Moloni: order_id=%s", order_id)
        return
    stmt = insert(MoloniExportJob).values(order_id=order_id, status="pending")
    stmt = stmt.on_conflict_do_nothing(constraint="uq_moloni_export_jobs_order")
    await db.execute(stmt)


async def order_has_prototype_items(db: AsyncSession, order_id: uuid.UUID) -> bool:
    """O pedido leva algum protótipo (código PROT-*)? O prefixo é reservado aos
    protótipos em EU, então basta o snapshot das linhas: vale mesmo que o
    protótipo seja desativado depois."""
    return (await db.execute(
        select(OrderItem.id).where(
            OrderItem.order_id == order_id,
            func.upper(OrderItem.product_code).like(PROTOTYPE_CODE_PREFIX + "%"),
        ).limit(1)
    )).scalar_one_or_none() is not None
