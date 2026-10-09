import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.moloni import MoloniExportJob
from app.services.moloni_exporter import deliver_job

async def run_once():
    async with AsyncSessionLocal() as db:
        jobs = list((await db.execute(select(MoloniExportJob).where(MoloniExportJob.status == "pending").order_by(MoloniExportJob.created_at).limit(10))).scalars())
        for job in jobs:
            job.attempts += 1
            try:
                job.moloni_document_id = await deliver_job(db, job); job.status = "delivered"; job.delivered_at = datetime.now(timezone.utc); job.last_error = None
            except Exception as exc:
                job.last_error = str(exc)[:500]; job.status = "dead_letter" if job.attempts >= settings.MOLONI_MAX_ATTEMPTS else "pending"
        await db.commit()

if __name__ == "__main__": asyncio.run(run_once())
