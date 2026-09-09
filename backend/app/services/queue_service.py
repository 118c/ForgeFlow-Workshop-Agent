"""排程任务提交层；本地同步执行，企业环境发送至 Celery。"""

import uuid

from ..core.config import get_settings
from ..core.redis_runtime import get_coordinator
from ..models.schemas import QueueJob, QueueJobStatus, SchedulingRequest
from ..repositories.task_repository import TaskRepository, get_task_repository
from .scheduling_service import SchedulingService


async def execute_job(job_id: str, repository: TaskRepository | None = None) -> QueueJob:
    repository = repository or get_task_repository()
    job = repository.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    repository.update_job(job_id, QueueJobStatus.RUNNING)
    lock_key = "schedule:%s:%s:%s" % (
        job.request.factory_id,
        job.request.workshop_id,
        job.request.production_date,
    )
    try:
        with get_coordinator().lock(lock_key, timeout=get_settings().celery_task_time_limit_seconds):
            result = await SchedulingService(repository).run(job.request)
        return repository.update_job(
            job_id,
            QueueJobStatus.SUCCEEDED,
            task_id=result.task_id,
            result=result,
        )
    except Exception as exc:
        repository.update_job(job_id, QueueJobStatus.FAILED, error=str(exc))
        raise


async def submit_job(
    request: SchedulingRequest,
    idempotency_key: str | None = None,
    repository: TaskRepository | None = None,
) -> QueueJob:
    repository = repository or get_task_repository()
    settings = get_settings()
    key = idempotency_key or "auto-%s" % uuid.uuid4().hex
    cached = get_coordinator().get_json("idempotency:%s" % key)
    if cached:
        existing = repository.get_job(cached["job_id"])
        if existing:
            return existing
    job = repository.create_job(request, key)
    get_coordinator().set_json(
        "idempotency:%s" % key,
        {"job_id": job.job_id},
        ttl_seconds=settings.idempotency_ttl_seconds,
    )
    if settings.task_execution_mode.lower() == "celery":
        from ..core.celery_app import celery_app

        celery_app.send_task("forgeflow.run_scheduling", args=[job.job_id], task_id=job.job_id)
        return job
    return await execute_job(job.job_id, repository)
