"""Celery 应用；企业模式以 Redis 作为 broker，任务事实仍写入 PostgreSQL。"""

from celery import Celery

from .config import get_settings


settings = get_settings()
celery_app = Celery(
    "forgeflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.celery_task_time_limit_seconds,
    result_expires=3600,
    beat_schedule={
        "dispatch-transactional-outbox": {
            "task": "forgeflow.dispatch_outbox",
            "schedule": 5.0,
        }
    },
)
