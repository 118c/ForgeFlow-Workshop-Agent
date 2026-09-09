"""SQLite 任务快照与审核审计仓储。"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from ..core.config import get_settings
from ..models.schemas import ReviewRecord, TaskSnapshot, utc_now


class VersionConflictError(RuntimeError):
    pass


class TaskRepository:
    def __init__(self, db_path: Optional[str] = None):
        configured = db_path or get_settings().task_db_path
        self.db_path = Path(configured).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduling_tasks (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_session ON scheduling_tasks(session_id, updated_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduling_task_history (
                    task_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, version)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_history ON scheduling_task_history(task_id, version DESC)"
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO scheduling_task_history(task_id, version, payload, recorded_at)
                SELECT task_id, version, payload, updated_at FROM scheduling_tasks
                """
            )

    def save(self, snapshot: TaskSnapshot, expected_version: Optional[int] = None) -> TaskSnapshot:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT version, created_at FROM scheduling_tasks WHERE task_id = ?", (snapshot.task_id,)
            ).fetchone()
            if row:
                current_version = int(row["version"])
                if expected_version is not None and current_version != expected_version:
                    raise VersionConflictError(
                        "任务版本已变化：期望 %s，当前 %s" % (expected_version, current_version)
                    )
                snapshot.version = current_version + 1
                snapshot.created_at = snapshot.created_at
            else:
                if expected_version not in (None, 0):
                    raise VersionConflictError("任务不存在，无法按版本更新")
                snapshot.version = 1
            snapshot.updated_at = utc_now()
            payload = snapshot.model_dump_json()
            conn.execute(
                """
                INSERT INTO scheduling_tasks(task_id, session_id, status, version, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    status=excluded.status,
                    version=excluded.version,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    snapshot.task_id,
                    snapshot.session_id,
                    snapshot.status.value,
                    snapshot.version,
                    payload,
                    snapshot.created_at.isoformat(),
                    snapshot.updated_at.isoformat(),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO scheduling_task_history(task_id, version, payload, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot.task_id, snapshot.version, payload, snapshot.updated_at.isoformat()),
            )
        return snapshot

    def get(self, task_id: str) -> Optional[TaskSnapshot]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM scheduling_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return TaskSnapshot.model_validate(json.loads(row["payload"])) if row else None

    def list_recent(self, limit: int = 20) -> List[TaskSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM scheduling_tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TaskSnapshot.model_validate(json.loads(row["payload"])) for row in rows]

    def list_versions(self, task_id: str) -> List[TaskSnapshot]:
        """返回任务的完整版本链，供审计和方案差异比较使用。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM scheduling_task_history WHERE task_id = ? ORDER BY version DESC",
                (task_id,),
            ).fetchall()
        return [TaskSnapshot.model_validate(json.loads(row["payload"])) for row in rows]

    def append_review(
        self, task_id: str, review: ReviewRecord, expected_version: Optional[int] = None
    ) -> TaskSnapshot:
        snapshot = self.get(task_id)
        if not snapshot:
            raise KeyError(task_id)
        snapshot.reviews.append(review)
        return self.save(snapshot, expected_version=expected_version)


_repository: Optional[TaskRepository] = None


def get_task_repository() -> TaskRepository:
    global _repository
    if _repository is None:
        _repository = TaskRepository()
    return _repository
