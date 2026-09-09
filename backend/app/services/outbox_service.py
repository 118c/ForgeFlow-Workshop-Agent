"""Transactional Outbox 发布器。"""

from datetime import timedelta
from typing import Dict, List

from ..agents.tools import get_toolset
from ..models.schemas import utc_now
from ..repositories.task_repository import TaskRepository, get_task_repository


async def dispatch_outbox_once(
    repository: TaskRepository | None = None,
    limit: int = 20,
) -> List[Dict[str, str]]:
    repository = repository or get_task_repository()
    results: List[Dict[str, str]] = []
    for event in repository.claim_outbox(limit):
        try:
            if event["event_type"] != "mes.plan.release.requested":
                raise ValueError("不支持的 Outbox 事件: %s" % event["event_type"])
            payload = event["payload"]
            receipt = await get_toolset(payload["data_source"]).publish_approved_plan(
                event["aggregate_id"], payload["plan"]
            )
            repository.mark_outbox_published(event["event_id"])
            results.append(
                {
                    "event_id": event["event_id"],
                    "status": "published",
                    "receipt": str(receipt.get("external_plan_id", "accepted")),
                }
            )
        except Exception as exc:
            attempts = int(event.get("attempts", 0)) + 1
            retry_seconds = min(300, 2**attempts)
            repository.mark_outbox_failed(event["event_id"], str(exc), utc_now() + timedelta(seconds=retry_seconds))
            results.append({"event_id": event["event_id"], "status": "retry", "error": str(exc)})
    return results
