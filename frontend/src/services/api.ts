import type { HistoricalReplayReport, PlanVersion, ResourceSnapshot, RolloutPolicy, SchedulingRequest, StreamEvent, TaskSnapshot } from '../types'

const API_BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || `接口响应异常 (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function streamSchedulingPlan(
  request: SchedulingRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/scheduling/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(request),
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`规划服务响应异常 (${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const dataLine = frame.split('\n').find((line) => line.startsWith('data: '))
      if (dataLine) onEvent(JSON.parse(dataLine.slice(6)) as StreamEvent)
    }
  }
}

export async function reviewTask(
  taskId: string,
  action: 'approve' | 'modify' | 'reject',
  expectedVersion: number,
  comment = '',
  modifications?: Record<string, unknown>,
): Promise<TaskSnapshot> {
  return requestJson<TaskSnapshot>(`/api/scheduling/tasks/${taskId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action,
      reviewer: '產線主管',
      comment,
      modifications,
      expected_version: expectedVersion,
    }),
  })
}

export async function getRuntime(): Promise<Record<string, any>> {
  return requestJson<Record<string, any>>('/api/config/runtime')
}

export async function listTasks(limit = 50): Promise<TaskSnapshot[]> {
  return requestJson<TaskSnapshot[]>(`/api/scheduling/tasks?limit=${limit}`)
}

export async function getTask(taskId: string): Promise<TaskSnapshot> {
  return requestJson<TaskSnapshot>(`/api/scheduling/tasks/${encodeURIComponent(taskId)}`)
}

export async function getResources(
  factoryId = 'FOX-SZ-01',
  workshopId = 'DIP-A',
  productionDate = '2026-09-10',
  source: 'mock' | 'real' = 'mock',
): Promise<ResourceSnapshot> {
  const params = new URLSearchParams({ factory_id: factoryId, workshop_id: workshopId, production_date: productionDate, source })
  return requestJson<ResourceSnapshot>(`/api/scheduling/resources?${params}`)
}

export async function getPlanVersions(filters: {
  taskId?: string
  workshopId?: string
  productionDate?: string
  limit?: number
} = {}): Promise<PlanVersion[]> {
  const params = new URLSearchParams()
  if (filters.taskId) params.set('task_id', filters.taskId)
  if (filters.workshopId) params.set('workshop_id', filters.workshopId)
  if (filters.productionDate) params.set('production_date', filters.productionDate)
  params.set('limit', String(filters.limit || 20))
  return requestJson<PlanVersion[]>(`/api/scheduling/plans/versions?${params}`)
}

export async function getRolloutPolicy(workshopId: string): Promise<RolloutPolicy> {
  return requestJson<RolloutPolicy>(`/api/scheduling/rollouts/${encodeURIComponent(workshopId)}`)
}

export async function getRolloutHistory(workshopId: string): Promise<RolloutPolicy[]> {
  return requestJson<RolloutPolicy[]>(`/api/scheduling/rollouts/${encodeURIComponent(workshopId)}/history`)
}

export async function updateRolloutPolicy(workshopId: string, policy: Pick<RolloutPolicy, 'mode' | 'traffic_percent' | 'updated_by' | 'reason'> & { expected_version: number }): Promise<RolloutPolicy> {
  return requestJson<RolloutPolicy>(`/api/scheduling/rollouts/${encodeURIComponent(workshopId)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policy) })
}

export async function rollbackRolloutPolicy(workshopId: string, expectedVersion: number): Promise<RolloutPolicy> {
  return requestJson<RolloutPolicy>(`/api/scheduling/rollouts/${encodeURIComponent(workshopId)}/rollback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ updated_by: 'release-operator', reason: '运行策略回退', expected_version: expectedVersion }) })
}

export async function runHistoricalReplay(sourceTaskId: string, dataSource: 'mock' | 'real'): Promise<HistoricalReplayReport> {
  return requestJson<HistoricalReplayReport>('/api/scheduling/replays', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_task_id: sourceTaskId, data_source: dataSource, requested_by: 'IE 工程师' }) })
}
