"""Agent 节点公共辅助函数。"""

import time
from typing import Any, Dict, Optional

from ...models.schemas import AgentStep, utc_now


NODE_LABELS = {
    "device_resource": "设备资源检索",
    "shift_query": "班组排班查询",
    "station_assign": "工位任务分配",
    "plan_generate": "作业方案生成",
    "human_review": "人工审核",
}


def finish_step(
    state: Dict[str, Any],
    node: str,
    started: float,
    output_summary: Optional[Dict[str, Any]] = None,
    error: Optional[Exception] = None,
) -> Dict[str, Any]:
    steps = list(state.get("steps", []))
    errors = list(state.get("errors", []))
    error_text = str(error) if error else None
    if error_text:
        errors.append("%s: %s" % (NODE_LABELS[node], error_text))
    step = AgentStep(
        node=node,
        label=NODE_LABELS[node],
        status="degraded" if error else "completed",
        started_at=utc_now(),
        duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
        output_summary=output_summary or {},
        error=error_text,
    )
    return {
        "current_node": node,
        "steps": steps + [step.model_dump(mode="json")],
        "errors": errors,
    }

