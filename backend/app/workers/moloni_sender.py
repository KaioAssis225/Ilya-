import asyncio
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.moloni import MoloniExportJob
from app.services.moloni_exporter import deliver_job

# Prazo para concluir um job reclamado. Se o worker morrer no meio, o job volta
# a ser elegível quando o lease vence, em vez de ficar preso em `processing`.
CLAIM_LEASE = timedelta(minutes=15)
_SECRET_PARAM = re.compile(r"(access_token|refresh_token|client_secret)=[^&\s'\"]+")


def _safe_error(exc: Exception) -> str:
    return _SECRET_PARAM.sub(r"\1=[REDACTED]", str(exc))[:500]


async def claim_next_job(db: AsyncSession, now: datetime) -> MoloniExportJob | None:
    """Reserva um job e confirma a reserva antes de falar com o Moloni.

    `SKIP LOCKED` + `processing` impedem que duas execuções entreguem o mesmo
    pedido (documento duplicado no Moloni).
    """
    job = (await db.execute(
        select(MoloniExportJob)
        .where(or_(
            and_(
                MoloniExportJob.status == "pending",
                or_(MoloniExportJob.next_attempt_at.is_(None), MoloniExportJob.next_attempt_at <= now),
            ),
            and_(MoloniExportJob.status == "processing", MoloniExportJob.next_attempt_at <= now),
        ))
        .order_by(MoloniExportJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if job is None:
        return None
    job.status = "processing"
    job.attempts += 1
    job.next_attempt_at = now + CLAIM_LEASE
    await db.commit()
    return job


async def _record_failure(db: AsyncSession, job: MoloniExportJob, exc: Exception) -> None:
    job_id = job.id
    try:
        # Preserva o que a entrega já gravou (token renovado, vínculos de
        # cliente/artigo criados no Moloni) para a nova tentativa não duplicar.
        await db.commit()
    except Exception:
        await db.rollback()
    job = await db.get(MoloniExportJob, job_id, populate_existing=True)
    now = datetime.now(timezone.utc)
    job.last_error = _safe_error(exc)
    if job.attempts >= settings.MOLONI_MAX_ATTEMPTS:
        job.status = "dead_letter"
        job.next_attempt_at = None
    else:
        job.status = "pending"
        job.next_attempt_at = now + timedelta(seconds=min(3600, 60 * (2 ** (job.attempts - 1))))
    await db.commit()


async def process_due_jobs(db: AsyncSession, *, limit: int = 10, deliver=deliver_job) -> int:
    """Entrega até `limit` jobs, cada um com commit próprio."""
    processed = 0
    while processed < limit:
        job = await claim_next_job(db, datetime.now(timezone.utc))
        if job is None:
            break
        processed += 1
        try:
            job.moloni_document_id = await deliver(db, job)
            job.status = "delivered"
            job.delivered_at = datetime.now(timezone.utc)
            job.last_error = None
            job.next_attempt_at = None
            await db.commit()
        except Exception as exc:
            await _record_failure(db, job, exc)
    return processed


async def run_once():
    if not settings.MOLONI_ENABLED:
        return
    async with AsyncSessionLocal() as db:
        await process_due_jobs(db)

if __name__ == "__main__": asyncio.run(run_once())
