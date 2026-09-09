"""车间作业规划领域模型。

API、LangGraph 状态和业务适配器共用这一套类型，避免节点之间传递无约束字典。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ALIYUN = "aliyun"
    OPENAI = "openai"


class DataSource(str, Enum):
    MOCK = "mock"
    REAL = "real"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    NEED_REVIEW = "need_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class QueueJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RolloutMode(str, Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    CANARY = "canary"
    ACTIVE = "active"


class ReviewAction(str, Enum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


class WorkOrder(BaseModel):
    order_id: str = Field(..., min_length=1, description="工单号")
    product_code: str = Field(..., min_length=1, description="产品料号")
    quantity: int = Field(..., gt=0, le=100000, description="计划数量")
    priority: int = Field(default=3, ge=1, le=5, description="优先级，5 最高")
    due_at: str = Field(..., description="交付时间，ISO 8601")
    process_route: List[str] = Field(default_factory=lambda: ["组装", "测试", "包装"])
    cycle_time_seconds: int = Field(default=45, gt=0, description="单件标准工时")


class SchedulingConstraints(BaseModel):
    preferred_team: Optional[str] = Field(default=None, description="优先班组")
    max_overtime_minutes: int = Field(default=60, ge=0, le=480)
    maintenance_window: Optional[str] = Field(default=None)
    allow_cross_line: bool = Field(default=True)
    notes: str = Field(default="")


class SchedulingRequest(BaseModel):
    session_id: str = Field(default="", description="会话 ID，用于偏好记忆隔离")
    task_name: str = Field(default="DIP 车间日计划")
    factory_id: str = Field(default="FOX-SZ-01")
    workshop_id: str = Field(default="DIP-A")
    production_date: str = Field(default="2026-09-10")
    shift_codes: List[str] = Field(default_factory=lambda: ["DAY", "NIGHT"])
    orders: List[WorkOrder] = Field(
        default_factory=lambda: [
            WorkOrder(
                order_id="MO-260910-081",
                product_code="MB-A17-PRO",
                quantity=1200,
                priority=5,
                due_at="2026-09-10T20:00:00+08:00",
                cycle_time_seconds=42,
            ),
            WorkOrder(
                order_id="MO-260910-096",
                product_code="MB-C08-LITE",
                quantity=860,
                priority=3,
                due_at="2026-09-11T08:00:00+08:00",
                cycle_time_seconds=55,
            ),
        ]
    )
    constraints: SchedulingConstraints = Field(default_factory=SchedulingConstraints)
    llm_provider: LLMProvider = Field(default=LLMProvider.DEEPSEEK)
    data_source: DataSource = Field(default=DataSource.MOCK)
    demo_mode: bool = Field(default=True, description="启用确定性规划器，不消耗 LLM token")
    require_human_review: bool = Field(default=True)


class AvailabilityWindow(BaseModel):
    start_at: str
    end_at: str


class DeviceResource(BaseModel):
    device_id: str
    name: str
    line_code: str
    station_code: str
    capability: List[str]
    status: str = "available"
    oee: float = Field(default=0.85, ge=0, le=1)
    capacity_per_hour: int = Field(default=80, gt=0)
    next_maintenance_at: Optional[str] = None
    calendar_windows: List[AvailabilityWindow] = Field(default_factory=list)


class ShiftResource(BaseModel):
    shift_code: str
    team_id: str
    team_name: str
    start_at: str
    end_at: str
    headcount: int = Field(ge=0)
    skill_tags: List[str] = Field(default_factory=list)
    attendance_rate: float = Field(default=1.0, ge=0, le=1)


class ResourceSnapshot(BaseModel):
    """一次可追溯的车间资源读取结果。"""

    factory_id: str
    workshop_id: str
    production_date: str
    source: DataSource
    source_version: str
    captured_at: datetime = Field(default_factory=utc_now)
    devices: List[DeviceResource] = Field(default_factory=list)
    shifts: List[ShiftResource] = Field(default_factory=list)


class StationAssignment(BaseModel):
    assignment_id: str
    order_id: str
    product_code: str
    process: str
    station_code: str
    device_id: str
    shift_code: str
    team_name: str
    tool_id: Optional[str] = None
    planned_quantity: int
    start_at: str
    end_at: str
    utilization: float = Field(ge=0, le=1.5)


class PlanRisk(BaseModel):
    level: str = Field(description="low/medium/high")
    code: str
    message: str
    mitigation: str


class PlanSummary(BaseModel):
    order_count: int
    planned_quantity: int
    device_count: int
    team_count: int
    estimated_completion_at: str
    average_utilization: float


class SchedulingPlan(BaseModel):
    plan_id: str
    title: str
    workshop_id: str
    production_date: str
    assignments: List[StationAssignment] = Field(default_factory=list)
    risks: List[PlanRisk] = Field(default_factory=list)
    summary: PlanSummary
    recommendations: List[str] = Field(default_factory=list)
    generated_by: str = "rule-fallback"
    degraded: bool = False
    solver_metadata: Dict[str, Any] = Field(default_factory=dict)


class PlanVersionMetrics(BaseModel):
    planned_quantity: int
    average_utilization: float
    risk_count: int
    overtime_minutes: int
    changeover_count: int
    on_time_rate: float = Field(ge=0, le=1)


class PlanVersion(BaseModel):
    """供方案比较页使用的稳定读模型。"""

    version_id: str
    task_id: str
    task_name: str
    revision: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    plan: SchedulingPlan
    metrics: PlanVersionMetrics


class AgentStep(BaseModel):
    node: str
    label: str
    status: str
    started_at: datetime = Field(default_factory=utc_now)
    duration_ms: Optional[int] = None
    input_summary: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ReviewRecord(BaseModel):
    action: ReviewAction
    reviewer: str
    comment: str = ""
    modifications: Optional[Dict[str, Any]] = None
    reviewed_at: datetime = Field(default_factory=utc_now)


class ReviewRequest(BaseModel):
    action: ReviewAction
    reviewer: str = Field(default="产线主管")
    comment: str = ""
    modifications: Optional[Dict[str, Any]] = None
    expected_version: Optional[int] = Field(default=None, ge=1, description="乐观锁版本")


class AgentState(BaseModel):
    """LangGraph 共享状态。每个节点只更新自己负责的字段。"""

    task_id: str
    trace_id: str
    request: Dict[str, Any]
    devices: List[Dict[str, Any]] = Field(default_factory=list)
    shifts: List[Dict[str, Any]] = Field(default_factory=list)
    work_orders: List[Dict[str, Any]] = Field(default_factory=list)
    materials: List[Dict[str, Any]] = Field(default_factory=list)
    tooling: List[Dict[str, Any]] = Field(default_factory=list)
    quality_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    solver_metadata: Dict[str, Any] = Field(default_factory=dict)
    assignments: List[Dict[str, Any]] = Field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    current_node: str = ""
    status: TaskStatus = TaskStatus.PENDING
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    need_human_review: bool = False
    human_feedback: Optional[Dict[str, Any]] = None
    llm_provider: str = "deepseek"
    data_source: str = "mock"
    started_at: datetime = Field(default_factory=utc_now)


class TaskSnapshot(BaseModel):
    task_id: str
    session_id: str
    trace_id: str
    status: TaskStatus
    current_node: str
    request: SchedulingRequest
    plan: Optional[SchedulingPlan] = None
    steps: List[AgentStep] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    reviews: List[ReviewRecord] = Field(default_factory=list)
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class QueueJob(BaseModel):
    job_id: str
    idempotency_key: str
    status: QueueJobStatus = QueueJobStatus.QUEUED
    request: SchedulingRequest
    task_id: Optional[str] = None
    result: Optional[TaskSnapshot] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RolloutPolicy(BaseModel):
    workshop_id: str
    mode: RolloutMode = RolloutMode.SHADOW
    traffic_percent: int = Field(default=0, ge=0, le=100)
    version: int = Field(default=1, ge=0)
    updated_by: str
    reason: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class RolloutUpdate(BaseModel):
    mode: RolloutMode
    traffic_percent: int = Field(default=0, ge=0, le=100)
    updated_by: str
    reason: str = ""
    expected_version: Optional[int] = Field(default=None, ge=0)


class RolloutRollbackRequest(BaseModel):
    updated_by: str
    reason: str = "紧急回退"
    expected_version: Optional[int] = Field(default=None, ge=1)


class HistoricalReplayRequest(BaseModel):
    source_task_id: str
    data_source: DataSource = DataSource.MOCK
    requested_by: str = "IE 工程师"


class HistoricalReplayReport(BaseModel):
    replay_id: str
    source_task_id: str
    replay_task_id: str
    status: str
    data_source: DataSource
    baseline_type: str
    baseline_metrics: PlanVersionMetrics
    replay_metrics: PlanVersionMetrics
    deltas: Dict[str, float]
    publish_blocked: bool = True
    requested_by: str
    created_at: datetime = Field(default_factory=utc_now)


class StreamEvent(BaseModel):
    session_id: str
    task_id: str
    trace_id: str
    step: int
    node: str
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    steps: List[AgentStep] = Field(default_factory=list)
