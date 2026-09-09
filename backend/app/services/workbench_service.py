"""业务工作台读模型：资源快照与方案版本比较。"""

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, time
from typing import List, Optional

from ..agents.tools import get_toolset
from ..models.schemas import (
    DataSource,
    PlanVersion,
    PlanVersionMetrics,
    ResourceSnapshot,
    SchedulingPlan,
    TaskSnapshot,
)
from ..repositories.task_repository import TaskRepository, get_task_repository


def _source_version(devices: list[dict], shifts: list[dict]) -> str:
    payload = json.dumps({"devices": devices, "shifts": shifts}, ensure_ascii=False, sort_keys=True, default=str)
    return "RS-%s" % hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10].upper()


async def read_resource_snapshot(
    factory_id: str,
    workshop_id: str,
    production_date: str,
    source: DataSource,
) -> ResourceSnapshot:
    toolset = get_toolset(source.value)
    devices, shifts = await asyncio.gather(
        toolset.query_available_devices(factory_id, workshop_id),
        toolset.query_shift_roster(factory_id, workshop_id, production_date, ["DAY", "NIGHT"]),
    )
    return ResourceSnapshot(
        factory_id=factory_id,
        workshop_id=workshop_id,
        production_date=production_date,
        source=source,
        source_version=_source_version(devices, shifts),
        devices=devices,
        shifts=shifts,
    )


def _minutes_after_shift(assignment_end: str) -> int:
    end_at = datetime.fromisoformat(assignment_end)
    regular_end = datetime.combine(end_at.date(), time(hour=20), tzinfo=end_at.tzinfo)
    return max(0, int((end_at - regular_end).total_seconds() // 60))


def _metrics(snapshot: TaskSnapshot, plan: SchedulingPlan) -> PlanVersionMetrics:
    assignments_by_device: dict[str, list] = defaultdict(list)
    completion_by_order: dict[str, datetime] = {}
    overtime_minutes = 0
    for assignment in plan.assignments:
        assignments_by_device[assignment.device_id].append(assignment)
        end_at = datetime.fromisoformat(assignment.end_at)
        completion_by_order[assignment.order_id] = max(completion_by_order.get(assignment.order_id, end_at), end_at)
        overtime_minutes += _minutes_after_shift(assignment.end_at)

    changeovers = 0
    for assignments in assignments_by_device.values():
        ordered = sorted(assignments, key=lambda item: item.start_at)
        changeovers += sum(
            current.product_code != previous.product_code
            for previous, current in zip(ordered, ordered[1:])
        )

    on_time = 0
    for order in snapshot.request.orders:
        completion = completion_by_order.get(order.order_id)
        if completion and completion <= datetime.fromisoformat(order.due_at):
            on_time += 1
    order_count = len(snapshot.request.orders)
    return PlanVersionMetrics(
        planned_quantity=plan.summary.planned_quantity,
        average_utilization=plan.summary.average_utilization,
        risk_count=len(plan.risks),
        overtime_minutes=overtime_minutes,
        changeover_count=changeovers,
        on_time_rate=on_time / order_count if order_count else 1.0,
    )


def _as_version(snapshot: TaskSnapshot) -> PlanVersion:
    assert snapshot.plan is not None
    return PlanVersion(
        version_id="%s:V%s" % (snapshot.task_id, snapshot.version),
        task_id=snapshot.task_id,
        task_name=snapshot.request.task_name,
        revision=snapshot.version,
        status=snapshot.status,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        plan=snapshot.plan,
        metrics=_metrics(snapshot, snapshot.plan),
    )


def list_plan_versions(
    task_id: Optional[str] = None,
    workshop_id: Optional[str] = None,
    production_date: Optional[str] = None,
    limit: int = 20,
    repository: Optional[TaskRepository] = None,
) -> List[PlanVersion]:
    repository = repository or get_task_repository()
    snapshots = repository.list_versions(task_id) if task_id else repository.list_recent(max(limit * 3, 30))
    snapshots = [
        item
        for item in snapshots
        if item.plan
        and (not workshop_id or item.request.workshop_id == workshop_id)
        and (not production_date or item.request.production_date == production_date)
    ]

    # 同一任务在多个图节点落盘时计划可能完全相同，只保留该方案的最新版本。
    seen: set[str] = set()
    result: List[PlanVersion] = []
    for snapshot in snapshots:
        assert snapshot.plan is not None
        signature = "%s:%s" % (
            snapshot.task_id,
            hashlib.sha256(snapshot.plan.model_dump_json().encode("utf-8")).hexdigest(),
        )
        if signature in seen:
            continue
        seen.add(signature)
        result.append(_as_version(snapshot))
        if len(result) >= limit:
            break
    return result
