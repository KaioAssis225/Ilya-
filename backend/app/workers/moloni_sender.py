import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.moloni import MoloniExportJob
from app.services.moloni_exporter import deliver_job

async def run_once():
    if not settings.MOLONI_ENABLED:
        return
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        jobs = list((await db.execute(
            select(MoloniExportJob)
            .where(MoloniExportJob.status == "pending")
            .where(or_(MoloniExportJob.next_attempt_at.is_(None), MoloniExportJob.next_attempt_at <= now))
            .order_by(MoloniExportJob.created_at)
            .limit(10)
        )).scalars())
        for job in jobs:
            job.attempts += 1
            try:
                job.moloni_document_id = await deliver_job(db, job)
                job.status = "delivered"
                job.delivered_at = now
                job.last_error = None
                job.next_attempt_at = None
            except Exception as exc:
                job.last_error = str(exc)[:500]
                if job.attempts >= settings.MOLONI_MAX_ATTEMPTS:
                    job.status = "dead_letter"
                    job.next_attempt_at = None
                else:
                    job.next_attempt_at = now + timedelta(seconds=min(3600, 60 * (2 ** (job.attempts - 1))))
        await db.commit()

if __name__ == "__main__": asyncio.run(run_once())
