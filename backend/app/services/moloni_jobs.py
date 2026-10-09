"""Fila transacional de exportação de pedidos EU para o Moloni."""
import uuid
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.moloni import MoloniExportJob

async def enqueue_finalized_eu_order(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Idempotente: finalizar duas vezes nunca pode gerar dois documentos."""
    stmt = insert(MoloniExportJob).values(order_id=order_id, status="pending")
    stmt = stmt.on_conflict_do_nothing(constraint="uq_moloni_export_jobs_order")
    await db.execute(stmt)
