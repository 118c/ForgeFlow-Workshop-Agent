"""SQLAlchemy 持久化层；本地使用 SQLite，企业环境切换 PostgreSQL。"""

import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

from ..core.config import get_settings
from ..models.schemas import QueueJob, QueueJobStatus, ReviewRecord, SchedulingRequest, TaskSnapshot, utc_now


class VersionConflictError(RuntimeError):
    pass


metadata = MetaData()

scheduling_tasks = Table(
    "scheduling_tasks",
    metadata,
    Column("task_id", String(64), primary_key=True),
    Column("session_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("idx_tasks_session", scheduling_tasks.c.session_id, scheduling_tasks.c.updated_at)

scheduling_task_history = Table(
    "scheduling_task_history",
    metadata,
    Column("task_id", String(64), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("payload", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)
Index("idx_task_history", scheduling_task_history.c.task_id, scheduling_task_history.c.version)

queue_jobs = Table(
    "queue_jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("idempotency_key", String(128), nullable=False, unique=True),
    Column("status", String(32), nullable=False),
    Column("request_payload", Text, nullable=False),
    Column("task_id", String(64), nullable=True),
    Column("result_payload", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
Index("idx_queue_jobs_status", queue_jobs.c.status, queue_jobs.c.updated_at)

outbox_events = Table(
    "outbox_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("event_type", String(96), nullable=False),
    Column("aggregate_id", String(64), nullable=False),
    Column("payload", Text, nullable=False),
    Column("status", String(24), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("error", Text, nullable=True),
)
Index("idx_outbox_pending", outbox_events.c.status, outbox_events.c.available_at)

shadow_runs = Table(
    "shadow_runs",
    metadata,
    Column("shadow_run_id", String(64), primary_key=True),
    Column("task_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("idx_shadow_runs_task", shadow_runs.c.task_id, shadow_runs.c.created_at)


def _database_url(value: Optional[str]) -> str:
    if not value:
        return get_settings().get_database_url()
    if "://" in value:
        return value
    path = Path(value).resolve().as_posix()
    return f"sqlite+pysqlite:///{path}"


class TaskRepository:
    def __init__(self, database_url: Optional[str] = None, engine: Optional[Engine] = None):
        settings = get_settings()
        self.database_url = _database_url(database_url)
        self._is_sqlite = self.database_url.startswith("sqlite")
        engine_options: Dict[str, Any] = {"pool_pre_ping": True}
        if self._is_sqlite:
            sqlite_database = make_url(self.database_url).database
            if sqlite_database and sqlite_database != ":memory:":
                Path(sqlite_database).resolve().parent.mkdir(parents=True, exist_ok=True)
            engine_options["connect_args"] = {"check_same_thread": False, "timeout": 10}
        else:
            engine_options.update(
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_recycle=1800,
            )
        self.engine = engine or create_engine(self.database_url, **engine_options)
        self._lock = threading.RLock()
        metadata.create_all(self.engine)

    @property
    def db_path(self) -> str:
        """兼容旧日志字段，并确保数据库密码不会被写入日志。"""
        return make_url(self.database_url).render_as_string(hide_password=True)

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(select(1))
        return True

    def save(
        self,
        snapshot: TaskSnapshot,
        expected_version: Optional[int] = None,
        outbox_event: Optional[Dict[str, Any]] = None,
    ) -> TaskSnapshot:
        with self._lock, self.engine.begin() as connection:
            statement = select(scheduling_tasks.c.version, scheduling_tasks.c.created_at).where(
                scheduling_tasks.c.task_id == snapshot.task_id
            )
            if not self._is_sqlite:
                statement = statement.with_for_update()
            row = connection.execute(statement).mappings().first()
            if row:
                current_version = int(row["version"])
                if expected_version is not None and current_version != expected_version:
                    raise VersionConflictError(
                        "任务版本已变化：期望 %s，当前 %s" % (expected_version, current_version)
                    )
                snapshot.version = current_version + 1
                result = connection.execute(
                    update(scheduling_tasks)
                    .where(
                        scheduling_tasks.c.task_id == snapshot.task_id,
                        scheduling_tasks.c.version == current_version,
                    )
                    .values(
                        session_id=snapshot.session_id,
                        status=snapshot.status.value,
                        version=snapshot.version,
                        payload="",
                        updated_at=utc_now(),
                    )
                )
                if result.rowcount != 1:
                    raise VersionConflictError("任务被其他实例更新，请刷新后重试")
            else:
                if expected_version not in (None, 0):
                    raise VersionConflictError("任务不存在，无法按版本更新")
                snapshot.version = 1
                connection.execute(
                    insert(scheduling_tasks).values(
                        task_id=snapshot.task_id,
                        session_id=snapshot.session_id,
                        status=snapshot.status.value,
                        version=snapshot.version,
                        payload="",
                        created_at=snapshot.created_at,
                        updated_at=utc_now(),
                    )
                )

            snapshot.updated_at = utc_now()
            payload = snapshot.model_dump_json()
            connection.execute(
                update(scheduling_tasks)
                .where(scheduling_tasks.c.task_id == snapshot.task_id)
                .values(
                    session_id=snapshot.session_id,
                    status=snapshot.status.value,
                    version=snapshot.version,
                    payload=payload,
                    updated_at=snapshot.updated_at,
                )
            )
            connection.execute(
                insert(scheduling_task_history).values(
                    task_id=snapshot.task_id,
                    version=snapshot.version,
                    payload=payload,
                    recorded_at=snapshot.updated_at,
                )
            )
            if outbox_event:
                connection.execute(
                    insert(outbox_events).values(
                        event_id=outbox_event["event_id"],
                        event_type=outbox_event["event_type"],
                        aggregate_id=outbox_event.get("aggregate_id", snapshot.task_id),
                        payload=json.dumps(outbox_event.get("payload", {}), ensure_ascii=False, default=str),
                        status="pending",
                        attempts=0,
                        available_at=utc_now(),
                        created_at=utc_now(),
                    )
                )
        return snapshot

    def get(self, task_id: str) -> Optional[TaskSnapshot]:
        with self.engine.connect() as connection:
            payload = connection.execute(
                select(scheduling_tasks.c.payload).where(scheduling_tasks.c.task_id == task_id)
            ).scalar_one_or_none()
        return TaskSnapshot.model_validate_json(payload) if payload else None

    def list_recent(self, limit: int = 20) -> List[TaskSnapshot]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(scheduling_tasks.c.payload).order_by(scheduling_tasks.c.updated_at.desc()).limit(limit)
            ).scalars().all()
        return [TaskSnapshot.model_validate_json(payload) for payload in rows if payload]

    def list_versions(self, task_id: str) -> List[TaskSnapshot]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(scheduling_task_history.c.payload)
                .where(scheduling_task_history.c.task_id == task_id)
                .order_by(scheduling_task_history.c.version.desc())
            ).scalars().all()
        return [TaskSnapshot.model_validate_json(payload) for payload in rows]

    def append_review(
        self, task_id: str, review: ReviewRecord, expected_version: Optional[int] = None
    ) -> TaskSnapshot:
        snapshot = self.get(task_id)
        if not snapshot:
            raise KeyError(task_id)
        snapshot.reviews.append(review)
        return self.save(snapshot, expected_version=expected_version)

    def create_job(self, request: SchedulingRequest, idempotency_key: str) -> QueueJob:
        existing = self.get_job_by_idempotency_key(idempotency_key)
        if existing:
            return existing
        job = QueueJob(
            job_id="job-%s" % uuid.uuid4().hex[:16],
            idempotency_key=idempotency_key,
            request=request,
        )
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(queue_jobs).values(
                        job_id=job.job_id,
                        idempotency_key=job.idempotency_key,
                        status=job.status.value,
                        request_payload=job.request.model_dump_json(),
                        created_at=job.created_at,
                        updated_at=job.updated_at,
                    )
                )
        except IntegrityError:
            # 多实例同时收到同一幂等键时，以先提交的记录为准。
            existing = self.get_job_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise
        return job

    def get_job_by_idempotency_key(self, key: str) -> Optional[QueueJob]:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(queue_jobs).where(queue_jobs.c.idempotency_key == key)
            ).mappings().first()
        return self._job_from_row(row) if row else None

    def get_job(self, job_id: str) -> Optional[QueueJob]:
        with self.engine.connect() as connection:
            row = connection.execute(select(queue_jobs).where(queue_jobs.c.job_id == job_id)).mappings().first()
        return self._job_from_row(row) if row else None

    def update_job(
        self,
        job_id: str,
        status: QueueJobStatus,
        task_id: Optional[str] = None,
        result: Optional[TaskSnapshot] = None,
        error: Optional[str] = None,
    ) -> QueueJob:
        values: Dict[str, Any] = {"status": status.value, "updated_at": utc_now(), "error": error}
        if task_id is not None:
            values["task_id"] = task_id
        if result is not None:
            values["result_payload"] = result.model_dump_json()
        with self.engine.begin() as connection:
            connection.execute(update(queue_jobs).where(queue_jobs.c.job_id == job_id).values(**values))
        job = self.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    @staticmethod
    def _job_from_row(row: Any) -> QueueJob:
        return QueueJob(
            job_id=row["job_id"],
            idempotency_key=row["idempotency_key"],
            status=QueueJobStatus(row["status"]),
            request=SchedulingRequest.model_validate_json(row["request_payload"]),
            task_id=row["task_id"],
            result=TaskSnapshot.model_validate_json(row["result_payload"]) if row["result_payload"] else None,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def claim_outbox(self, limit: int = 20) -> List[Dict[str, Any]]:
        now = utc_now()
        lease_until = now + timedelta(seconds=get_settings().outbox_claim_lease_seconds)
        with self.engine.begin() as connection:
            statement = (
                select(outbox_events)
                .where(
                    or_(outbox_events.c.status == "pending", outbox_events.c.status == "processing"),
                    outbox_events.c.available_at <= now,
                )
                .order_by(outbox_events.c.created_at)
                .limit(limit)
            )
            if not self._is_sqlite:
                statement = statement.with_for_update(skip_locked=True)
            rows = [dict(row) for row in connection.execute(statement).mappings().all()]
            if rows:
                connection.execute(
                    update(outbox_events)
                    .where(outbox_events.c.event_id.in_([row["event_id"] for row in rows]))
                    .values(status="processing", available_at=lease_until)
                )
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def mark_outbox_published(self, event_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(outbox_events)
                .where(outbox_events.c.event_id == event_id)
                .values(status="published", published_at=utc_now(), error=None)
            )

    def mark_outbox_failed(self, event_id: str, error: str, retry_at: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(outbox_events)
                .where(outbox_events.c.event_id == event_id)
                .values(
                    status="pending",
                    attempts=outbox_events.c.attempts + 1,
                    available_at=retry_at,
                    error=error[:2000],
                )
            )

    def save_shadow_report(self, report: Any) -> None:
        payload = report.model_dump_json()
        with self.engine.begin() as connection:
            connection.execute(
                insert(shadow_runs).values(
                    shadow_run_id=report.shadow_run_id,
                    task_id=report.task_id,
                    status=report.status,
                    payload=payload,
                    created_at=report.created_at,
                )
            )

    def get_shadow_report(self, shadow_run_id: str, model: Any) -> Optional[Any]:
        with self.engine.connect() as connection:
            payload = connection.execute(
                select(shadow_runs.c.payload).where(shadow_runs.c.shadow_run_id == shadow_run_id)
            ).scalar_one_or_none()
        return model.model_validate_json(payload) if payload else None

    def clear_all(self) -> None:
        """仅供隔离测试使用。"""
        with self.engine.begin() as connection:
            for table in (shadow_runs, outbox_events, queue_jobs, scheduling_task_history, scheduling_tasks):
                connection.execute(delete(table))


_repository: Optional[TaskRepository] = None


def get_task_repository() -> TaskRepository:
    global _repository
    if _repository is None:
        _repository = TaskRepository()
    return _repository
