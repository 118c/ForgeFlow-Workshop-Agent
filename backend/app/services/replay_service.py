"""历史工单回放与人工计划基准对照。"""

import uuid
from typing import Optional

from ..models.schemas import HistoricalReplayReport, HistoricalReplayRequest
from ..repositories.task_repository import TaskRepository, get_task_repository
from .business_gateway import WorkshopGateway, get_workshop_gateway
from .scheduling_service import SchedulingService
from .workbench_service import calculate_plan_metrics


async def run_historical_replay(command: HistoricalReplayRequest, repository: Optional[TaskRepository] = None, gateway: Optional[WorkshopGateway] = None) -> HistoricalReplayReport:
    repository = repository or get_task_repository()
    source = repository.get(command.source_task_id)
    if not source or not source.plan:
        raise KeyError(command.source_task_id)
    replay_request = source.request.model_copy(deep=True)
    replay_request.session_id = "replay-%s" % uuid.uuid4().hex[:12]
    replay_request.data_source = command.data_source
    replay_request.demo_mode = True
    replay_request.require_human_review = False
    replay = await SchedulingService(repository).run(replay_request)
    if not replay.plan:
        raise RuntimeError("历史回放未生成候选方案")

    gateway = gateway or get_workshop_gateway(command.data_source.value)
    validation_data = await gateway.collect_validation_snapshot(replay_request)
    replay_metrics = calculate_plan_metrics(replay, replay.plan)
    if validation_data.manual_plan:
        baseline_type = "manual_plan"
        baseline = validation_data.manual_plan.metrics
    else:
        baseline_type = "source_plan"
        baseline = calculate_plan_metrics(source, source.plan)
    deltas = {
        "on_time_rate": replay_metrics.on_time_rate - baseline.on_time_rate,
        "average_utilization": replay_metrics.average_utilization - baseline.average_utilization,
        "overtime_minutes": float(replay_metrics.overtime_minutes - baseline.overtime_minutes),
        "changeover_count": float(replay_metrics.changeover_count - baseline.changeover_count),
    }
    status = "passed" if deltas["on_time_rate"] >= 0 and deltas["overtime_minutes"] <= 0 else "warning"
    report = HistoricalReplayReport(replay_id="REPLAY-%s" % uuid.uuid4().hex[:12].upper(), source_task_id=source.task_id, replay_task_id=replay.task_id, status=status, data_source=command.data_source, baseline_type=baseline_type, baseline_metrics=baseline, replay_metrics=replay_metrics, deltas=deltas, publish_blocked=True, requested_by=command.requested_by)
    repository.save_replay_report(report)
    return report
