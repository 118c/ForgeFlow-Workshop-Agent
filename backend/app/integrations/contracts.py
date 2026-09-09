"""MES/WMS/EAM/HR/QMS 的边界契约与影子验证结果。"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..models.schemas import DeviceResource, PlanVersionMetrics, ShiftResource, WorkOrder, utc_now


class SourceMetadata(BaseModel):
    system: Literal["MES", "WMS", "EAM", "HR", "QMS"]
    source_version: str = Field(min_length=1)
    captured_at: datetime


class MaterialReadiness(BaseModel):
    order_id: str
    material_code: str
    required_quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    ready_at: Optional[datetime] = None
    lot_codes: List[str] = Field(default_factory=list)


class ToolingResource(BaseModel):
    tool_id: str
    name: str
    compatible_products: List[str]
    required_processes: List[str] = Field(default_factory=lambda: ["组装"])
    status: Literal["available", "reserved", "maintenance"] = "available"
    available_from: Optional[datetime] = None


class QualityConstraint(BaseModel):
    product_code: str
    quality_status: Literal["released", "hold", "blocked"] = "released"
    first_article_required: bool = False
    inspection_minutes: int = Field(default=0, ge=0)
    blocked_lots: List[str] = Field(default_factory=list)


class ManualPlanReference(BaseModel):
    reference_id: str
    workshop_id: str
    production_date: str
    metrics: PlanVersionMetrics


class ValidationDataSnapshot(BaseModel):
    snapshot_id: str
    captured_at: datetime = Field(default_factory=utc_now)
    sources: Dict[str, SourceMetadata]
    work_orders: List[WorkOrder]
    devices: List[DeviceResource]
    shifts: List[ShiftResource]
    materials: List[MaterialReadiness]
    tooling: List[ToolingResource]
    quality_constraints: List[QualityConstraint]
    manual_plan: Optional[ManualPlanReference] = None


class ShadowRunRequest(BaseModel):
    task_id: str
    data_source: Literal["mock", "real"] = "real"


class ValidationCheck(BaseModel):
    code: str
    category: Literal["freshness", "order", "equipment", "workforce", "material", "tooling", "quality"]
    severity: Literal["info", "warning", "critical"]
    passed: bool
    message: str
    affected_ids: List[str] = Field(default_factory=list)


class ShadowComparison(BaseModel):
    agent_metrics: PlanVersionMetrics
    manual_metrics: Optional[PlanVersionMetrics] = None
    on_time_rate_delta: Optional[float] = None
    utilization_delta: Optional[float] = None
    overtime_minutes_delta: Optional[int] = None
    changeover_count_delta: Optional[int] = None


class ShadowRunReport(BaseModel):
    shadow_run_id: str
    task_id: str
    status: Literal["passed", "warning", "failed"]
    data_source: Literal["mock", "real"]
    snapshot_id: str
    source_versions: Dict[str, str]
    checks: List[ValidationCheck]
    comparison: ShadowComparison
    publish_blocked: bool = True
    created_at: datetime = Field(default_factory=utc_now)
