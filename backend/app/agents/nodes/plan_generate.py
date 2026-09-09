import json
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from ...core.llm import LLMFactory, extract_json_object
from ...models.schemas import PlanRisk, PlanSummary, SchedulingPlan
from .common import finish_step


def _rule_plan(state: Dict[str, Any], generated_by: str, degraded: bool = False) -> SchedulingPlan:
    request = state["request"]
    assignments = state.get("assignments", [])
    orders = state.get("work_orders") or request.get("orders", [])
    end_times = [item["end_at"] for item in assignments]
    completion = max(end_times) if end_times else request["production_date"] + "T20:00:00+08:00"
    utilizations = [float(item["utilization"]) for item in assignments]
    risks: List[PlanRisk] = []
    if state.get("errors"):
        risks.append(PlanRisk(level="medium", code="DATA_DEGRADED", message="部分业务数据不可用，已使用安全基线资源", mitigation="主管审核设备与班组后再下发"))
    if any(item > 1 for item in utilizations):
        risks.append(PlanRisk(level="high", code="CAPACITY_OVERLOAD", message="至少一个工位负载超过单班额定产能", mitigation="拆分批次到夜班或启用跨线生产"))
    if any(float(item.get("attendance_rate", 1)) < 0.9 for item in state.get("shifts", [])):
        risks.append(PlanRisk(level="medium", code="ATTENDANCE_LOW", message="夜班到岗率低于 90%", mitigation="预留 2 名多能工并在班前复核到岗"))
    if not risks:
        risks.append(PlanRisk(level="low", code="NORMAL", message="资源与交期约束均在安全区间", mitigation="按标准班前点检执行"))
    return SchedulingPlan(
        plan_id="PLAN-%s" % state["task_id"][-8:].upper(),
        title=request["task_name"],
        workshop_id=request["workshop_id"],
        production_date=request["production_date"],
        assignments=assignments,
        risks=risks,
        summary=PlanSummary(
            order_count=len(orders),
            planned_quantity=sum(int(item["quantity"]) for item in orders),
            device_count=len({item["device_id"] for item in assignments}),
            team_count=len({item["team_name"] for item in assignments}),
            estimated_completion_at=completion,
            average_utilization=round(statistics.mean(utilizations), 2) if utilizations else 0,
        ),
        recommendations=["高优工单优先锁定首件检验", "换线前执行物料齐套确认", "班后回写实际产量与停机原因"],
        generated_by=generated_by,
        degraded=degraded,
        solver_metadata=state.get("solver_metadata", {}),
    )


async def plan_generate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    request = state["request"]
    plan = _rule_plan(state, "ortools-cp-sat", bool(state.get("errors")))
    provider = state["llm_provider"]
    llm_error = None
    if not request.get("demo_mode"):
        prompt = """你是制造业生产计划专家。根据下方确定性排程结果，只补充 title、risks、recommendations，绝不修改 assignments 和 summary。只返回 JSON。\n%s""" % json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)
        try:
            content, provider = await LLMFactory.invoke_with_failover(prompt, provider)
            enrichment = extract_json_object(content)
            merged = plan.model_dump(mode="json")
            for key in ("title", "risks", "recommendations"):
                if key in enrichment:
                    merged[key] = enrichment[key]
            merged["generated_by"] = "llm:%s" % provider
            plan = SchedulingPlan.model_validate(merged)
        except Exception as exc:
            llm_error = exc
            plan.degraded = True

    update = finish_step(
        state,
        "plan_generate",
        started,
        {"plan_id": plan.plan_id, "risk_count": len(plan.risks), "generated_by": plan.generated_by, "fallback": bool(llm_error)},
        llm_error,
    )
    update.update({"plan": plan.model_dump(mode="json"), "llm_provider": provider})
    return update
