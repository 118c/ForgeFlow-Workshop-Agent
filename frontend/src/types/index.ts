export type TaskStatus = 'pending' | 'processing' | 'need_review' | 'approved' | 'rejected' | 'failed'
export type NodeStatus = 'waiting' | 'running' | 'completed' | 'degraded'

export interface WorkOrder {
  order_id: string
  product_code: string
  quantity: number
  priority: number
  due_at: string
  process_route: string[]
  cycle_time_seconds: number
}
export interface SchedulingRequest {
  session_id?: string
  task_name: string
  factory_id: string
  workshop_id: string
  production_date: string
  shift_codes: string[]
  orders: WorkOrder[]
  constraints: {
    preferred_team?: string
    max_overtime_minutes: number
    maintenance_window?: string
    allow_cross_line: boolean
    notes: string
  }
  llm_provider: 'deepseek' | 'aliyun' | 'openai'
  data_source: 'mock' | 'real'
  demo_mode: boolean
  require_human_review: boolean
}

export interface AgentStep {
  node: string
  label: string
  status: string
  duration_ms?: number
  output_summary: Record<string, unknown>
  error?: string
}

export interface ReviewRecord {
  action: 'approve' | 'modify' | 'reject'
  reviewer: string
  comment: string
  modifications?: Record<string, unknown>
  reviewed_at: string
}

export interface Assignment {
  assignment_id: string
  order_id: string
  product_code: string
  process: string
  station_code: string
  device_id: string
  shift_code: string
  team_name: string
  planned_quantity: number
  start_at: string
  end_at: string
  utilization: number
}

export interface SchedulingPlan {
  plan_id: string
  title: string
  workshop_id: string
  production_date: string
  assignments: Assignment[]
  risks: Array<{ level: string; code: string; message: string; mitigation: string }>
  summary: {
    order_count: number
    planned_quantity: number
    device_count: number
    team_count: number
    estimated_completion_at: string
    average_utilization: number
  }
  recommendations: string[]
  generated_by: string
  degraded: boolean
}

export interface DeviceResource {
  device_id: string
  name: string
  line_code: string
  station_code: string
  capability: string[]
  status: string
  oee: number
  capacity_per_hour: number
  next_maintenance_at?: string
}

export interface ShiftResource {
  shift_code: string
  team_id: string
  team_name: string
  start_at: string
  end_at: string
  headcount: number
  skill_tags: string[]
  attendance_rate: number
}

export interface ResourceSnapshot {
  factory_id: string
  workshop_id: string
  production_date: string
  source: 'mock' | 'real'
  source_version: string
  captured_at: string
  devices: DeviceResource[]
  shifts: ShiftResource[]
}

export interface PlanVersion {
  version_id: string
  task_id: string
  task_name: string
  revision: number
  status: TaskStatus
  created_at: string
  updated_at: string
  plan: SchedulingPlan
  metrics: {
    planned_quantity: number
    average_utilization: number
    risk_count: number
    overtime_minutes: number
    changeover_count: number
    on_time_rate: number
  }
}

export interface TaskSnapshot {
  task_id: string
  session_id: string
  trace_id: string
  status: TaskStatus
  current_node: string
  request: SchedulingRequest
  plan?: SchedulingPlan
  steps: AgentStep[]
  errors: string[]
  warnings: string[]
  reviews: ReviewRecord[]
  version: number
  created_at: string
  updated_at: string
}

export interface StreamEvent {
  session_id: string
  task_id: string
  trace_id: string
  step: number
  node: string
  status: string
  message: string
  data?: Record<string, any>
  steps: AgentStep[]
}
