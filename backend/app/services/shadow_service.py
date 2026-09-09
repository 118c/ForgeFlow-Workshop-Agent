"""生产资料只读影子验证；不会调用 MES 发布接口。"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from ..core.config import get_settings
from ..integrations.contracts import ShadowComparison, ShadowRunReport, ShadowRunRequest, ValidationCheck
from ..repositories.task_repository import TaskRepository, get_task_repository
from .business_gateway import WorkshopGateway, get_workshop_gateway
from .workbench_service import calculate_plan_metrics


def _check(code: str, category: str, passed: bool, message: str, affected: list[str], severity: str = "critical") -> ValidationCheck:
    return ValidationCheck(code=code, category=category, severity=severity, passed=passed, message=message, affected_ids=affected)


async def run_shadow_validation(
    command: ShadowRunRequest,
    repository: Optional[TaskRepository] = None,
    gateway: Optional[WorkshopGateway] = None,
) -> ShadowRunReport:
    repository = repository or get_task_repository()
    task = repository.get(command.task_id)
    if not task or not task.plan:
        raise KeyError(command.task_id)
    gateway = gateway or get_workshop_gateway(command.data_source)
    data = await gateway.collect_validation_snapshot(task.request)
    now = datetime.now(timezone.utc)
    max_age = get_settings().shadow_data_max_age_seconds
    stale = [name for name, meta in data.sources.items() if (now - meta.captured_at.astimezone(timezone.utc)).total_seconds() > max_age]
    checks = [_check("DATA_FRESHNESS", "freshness", not stale, "五套系统资料均在允许时效内" if not stale else "存在逾时资料来源", stale)]

    assignment_keys = {(a.order_id, a.process) for a in task.plan.assignments}
    missing_routes = ["%s:%s" % (o.order_id, process) for o in data.work_orders for process in o.process_route if (o.order_id, process) not in assignment_keys]
    checks.append(_check("ORDER_ROUTE_COVERAGE", "order", not missing_routes, "所有 MES 工单制程均已排入" if not missing_routes else "部分工单制程未排入", missing_routes))

    devices = {item.device_id: item for item in data.devices}
    invalid_devices = [a.assignment_id for a in task.plan.assignments if a.device_id not in devices or devices[a.device_id].status != "available" or a.process not in devices[a.device_id].capability]
    checks.append(_check("EQUIPMENT_ELIGIBILITY", "equipment", not invalid_devices, "设备状态与制程能力相符" if not invalid_devices else "设备状态或能力不符", invalid_devices))

    shifts = {item.shift_code: item for item in data.shifts}
    invalid_skills = [a.assignment_id for a in task.plan.assignments if a.shift_code not in shifts or a.process not in shifts[a.shift_code].skill_tags]
    checks.append(_check("WORKFORCE_SKILL", "workforce", not invalid_skills, "班组技能覆盖全部派工" if not invalid_skills else "班组技能不符合制程", invalid_skills))

    material_by_order = {item.order_id: item for item in data.materials}
    shortages = [o.order_id for o in data.work_orders if o.order_id not in material_by_order or material_by_order[o.order_id].available_quantity < material_by_order[o.order_id].required_quantity]
    checks.append(_check("MATERIAL_READINESS", "material", not shortages, "WMS 齐套数量满足计划" if not shortages else "存在物料缺口", shortages))

    available_products = {product for tool in data.tooling if tool.status == "available" for product in tool.compatible_products}
    missing_tools = [o.product_code for o in data.work_orders if o.product_code not in available_products]
    checks.append(_check("TOOLING_AVAILABILITY", "tooling", not missing_tools, "生产治具均可用" if not missing_tools else "产品缺少可用治具", missing_tools))

    quality_by_product = {item.product_code: item for item in data.quality_constraints}
    quality_blocks = [o.product_code for o in data.work_orders if o.product_code not in quality_by_product or quality_by_product[o.product_code].quality_status != "released"]
    checks.append(_check("QUALITY_RELEASE", "quality", not quality_blocks, "QMS 放行状态正常" if not quality_blocks else "产品尚未通过质量放行", quality_blocks))

    agent_metrics = calculate_plan_metrics(task, task.plan)
    manual_metrics = data.manual_plan.metrics if data.manual_plan else None
    comparison = ShadowComparison(
        agent_metrics=agent_metrics,
        manual_metrics=manual_metrics,
        on_time_rate_delta=agent_metrics.on_time_rate - manual_metrics.on_time_rate if manual_metrics else None,
        utilization_delta=agent_metrics.average_utilization - manual_metrics.average_utilization if manual_metrics else None,
        overtime_minutes_delta=agent_metrics.overtime_minutes - manual_metrics.overtime_minutes if manual_metrics else None,
        changeover_count_delta=agent_metrics.changeover_count - manual_metrics.changeover_count if manual_metrics else None,
    )
    failed_critical = any(not item.passed and item.severity == "critical" for item in checks)
    failed_warning = any(not item.passed and item.severity == "warning" for item in checks)
    report = ShadowRunReport(
        shadow_run_id="SHADOW-%s" % uuid.uuid4().hex[:12].upper(), task_id=task.task_id,
        status="failed" if failed_critical else ("warning" if failed_warning else "passed"), data_source=command.data_source,
        snapshot_id=data.snapshot_id, source_versions={name: meta.source_version for name, meta in data.sources.items()},
        checks=checks, comparison=comparison, publish_blocked=True,
    )
    repository.save_shadow_report(report)
    return report
