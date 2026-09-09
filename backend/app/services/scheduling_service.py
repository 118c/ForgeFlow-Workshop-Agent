"""调度用例层：驱动图、持久化快照并处理人工审核。"""

import copy
import uuid
from typing import Any, AsyncIterator, Dict, Optional

from ..agents.graph import get_graph
from ..core.config import get_settings
from ..core.memory import get_memory_manager
from ..models.schemas import (
    AgentState,
    ReviewAction,
    ReviewRecord,
    ReviewRequest,
    SchedulingPlan,
    SchedulingRequest,
    StreamEvent,
    TaskSnapshot,
    TaskStatus,
)
from ..repositories.task_repository import TaskRepository, get_task_repository
from .outbox_service import dispatch_outbox_once


NODE_MESSAGES = {
    "device_resource": "设备资源检索完成",
    "shift_query": "班组与工单数据已就绪",
    "station_assign": "工位任务分配完成",
    "plan_generate": "作业方案已生成",
    "human_review": "方案已进入人工审核",
}


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class SchedulingService:
    def __init__(self, repository: Optional[TaskRepository] = None):
        self.repository = repository or get_task_repository()

    def _prepare_request(self, request: SchedulingRequest) -> SchedulingRequest:
        request = request.model_copy(deep=True)
        if not request.session_id:
            request.session_id = "session-%s" % uuid.uuid4().hex[:12]
        memory = get_memory_manager().get_memory(request.session_id)
        if not request.constraints.preferred_team:
            request.constraints.preferred_team = memory.get_preference("preferred_team")
        if request.constraints.preferred_team:
            memory.set_preference("preferred_team", request.constraints.preferred_team)
        memory.set_preference("workshop_id", request.workshop_id)
        memory.set_preference("max_overtime_minutes", request.constraints.max_overtime_minutes)
        return request

    def _initial_state(self, request: SchedulingRequest, task_id: str, trace_id: str) -> Dict[str, Any]:
        state = AgentState(
            task_id=task_id,
            trace_id=trace_id,
            request=request.model_dump(mode="json"),
            status=TaskStatus.PROCESSING,
            llm_provider=request.llm_provider.value,
            data_source=request.data_source.value,
        )
        return state.model_dump(mode="json")

    def _snapshot(self, state: Dict[str, Any]) -> TaskSnapshot:
        existing = self.repository.get(state["task_id"])
        return TaskSnapshot(
            task_id=state["task_id"],
            session_id=state["request"]["session_id"],
            trace_id=state["trace_id"],
            status=TaskStatus(state["status"]),
            current_node=state.get("current_node", ""),
            request=SchedulingRequest.model_validate(state["request"]),
            plan=SchedulingPlan.model_validate(state["plan"]) if state.get("plan") else None,
            steps=state.get("steps", []),
            errors=state.get("errors", []),
            warnings=state.get("warnings", []),
            reviews=existing.reviews if existing else [],
            version=existing.version if existing else 1,
            created_at=existing.created_at if existing else state.get("started_at"),
        )

    async def stream(self, request: SchedulingRequest) -> AsyncIterator[StreamEvent]:
        request = self._prepare_request(request)
        task_id = "task-%s" % uuid.uuid4().hex[:16]
        trace_id = "trace-%s" % uuid.uuid4().hex[:12]
        state = self._initial_state(request, task_id, trace_id)
        self.repository.save(self._snapshot(state))
        yield StreamEvent(
            session_id=request.session_id,
            task_id=task_id,
            trace_id=trace_id,
            step=0,
            node="init",
            status="processing",
            message="调度任务已创建，开始编排",
            data={"data_source": request.data_source.value, "demo_mode": request.demo_mode},
        )

        graph = get_graph()
        config = {"configurable": {"thread_id": task_id}}
        step_number = 0
        async for graph_update in graph.astream(state, config=config, stream_mode="updates"):
            for node, update in graph_update.items():
                step_number += 1
                state.update(update)
                if node == "plan_generate" and not request.require_human_review:
                    state["status"] = TaskStatus.APPROVED.value
                saved = self.repository.save(self._snapshot(state))
                last_step = saved.steps[-1] if saved.steps else None
                yield StreamEvent(
                    session_id=request.session_id,
                    task_id=task_id,
                    trace_id=trace_id,
                    step=step_number,
                    node=node,
                    status=last_step.status if last_step else state["status"],
                    message=NODE_MESSAGES.get(node, "节点执行完成"),
                    data={
                        "summary": last_step.output_summary if last_step else {},
                        "plan": saved.plan.model_dump(mode="json") if node in ("plan_generate", "human_review") and saved.plan else None,
                        "task_status": saved.status.value,
                        "version": saved.version,
                        "errors": saved.errors,
                    },
                    steps=saved.steps,
                )

        final = self.repository.get(task_id)
        yield StreamEvent(
            session_id=request.session_id,
            task_id=task_id,
            trace_id=trace_id,
            step=step_number + 1,
            node="complete",
            status=final.status.value if final else "failed",
            message="方案等待产线主管审核" if final and final.status == TaskStatus.NEED_REVIEW else "调度任务完成",
            data=final.model_dump(mode="json") if final else None,
            steps=final.steps if final else [],
        )

    async def run(self, request: SchedulingRequest) -> TaskSnapshot:
        task_id = None
        async for event in self.stream(request):
            task_id = event.task_id
        snapshot = self.repository.get(task_id or "")
        if not snapshot:
            raise RuntimeError("调度任务未产生快照")
        return snapshot

    async def review(self, task_id: str, command: ReviewRequest) -> TaskSnapshot:
        snapshot = self.repository.get(task_id)
        if not snapshot:
            raise KeyError(task_id)
        if snapshot.status != TaskStatus.NEED_REVIEW:
            raise ValueError("只有 need_review 状态的任务可审核")
        if command.action == ReviewAction.MODIFY:
            if not command.modifications:
                raise ValueError("modify 操作必须提供 modifications")
            if not snapshot.plan:
                raise ValueError("任务没有可修改的计划")
            merged = _deep_merge(snapshot.plan.model_dump(mode="json"), command.modifications)
            snapshot.plan = SchedulingPlan.model_validate(merged)
            snapshot.status = TaskStatus.APPROVED
        elif command.action == ReviewAction.APPROVE:
            snapshot.status = TaskStatus.APPROVED
        else:
            snapshot.status = TaskStatus.REJECTED
        snapshot.current_node = "human_review"
        snapshot.reviews.append(
            ReviewRecord(
                action=command.action,
                reviewer=command.reviewer,
                comment=command.comment,
                modifications=command.modifications,
            )
        )
        outbox_event = None
        if snapshot.status == TaskStatus.APPROVED and snapshot.plan:
            outbox_event = {
                "event_id": "evt-%s" % uuid.uuid4().hex,
                "event_type": "mes.plan.release.requested",
                "aggregate_id": task_id,
                "payload": {
                    "data_source": snapshot.request.data_source.value,
                    "plan": snapshot.plan.model_dump(mode="json"),
                },
            }
            if get_settings().task_execution_mode.lower() == "celery":
                snapshot.warnings.append("MES 下发请求已写入可靠事件队列")

        # 审核事实与 MES 下发意图在同一数据库事务中提交。
        saved = self.repository.save(
            snapshot,
            expected_version=command.expected_version,
            outbox_event=outbox_event,
        )
        if outbox_event and get_settings().task_execution_mode.lower() != "celery":
            delivery = await dispatch_outbox_once(self.repository, limit=1)
            if delivery and delivery[0]["status"] == "published":
                saved.warnings.append("MES 下发回执: %s" % delivery[0]["receipt"])
            elif delivery:
                saved.warnings.append("MES 下发失败，已进入重试队列: %s" % delivery[0].get("error", "unknown"))
            saved = self.repository.save(saved)
        return saved


_service: Optional[SchedulingService] = None


def get_scheduling_service() -> SchedulingService:
    global _service
    if _service is None:
        _service = SchedulingService()
    return _service
