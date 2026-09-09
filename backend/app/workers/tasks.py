"""Celery 任务入口。"""

import asyncio

from ..core.celery_app import celery_app
from ..services.outbox_service import dispatch_outbox_once
from ..services.queue_service import execute_job


@celery_app.task(name="forgeflow.run_scheduling", bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_scheduling(self, job_id: str) -> dict:
    del self
    job = asyncio.run(execute_job(job_id))
    return {"job_id": job.job_id, "task_id": job.task_id, "status": job.status.value}


@celery_app.task(name="forgeflow.dispatch_outbox")
def dispatch_outbox() -> list[dict]:
    return asyncio.run(dispatch_outbox_once())
