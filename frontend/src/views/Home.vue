<template>
  <div class="shell">
    <aside class="rail">
      <div class="brand">
        <div class="brand-mark"><span></span><span></span><span></span></div>
        <div><strong>FORGEFLOW</strong><small>{{ t('brandSubtitle') }}</small></div>
      </div>
      <nav :aria-label="t('mainNav')">
        <button :class="['nav-item',{active:activeView==='planning'}]" @click="activeView='planning'"><span>⌁</span>{{ t('navPlanning') }}<i>01</i></button>
        <button :class="['nav-item',{active:activeView==='tasks'}]" @click="activeView='tasks'"><span>▦</span>{{ t('navTasks') }}<i>02</i></button>
        <button :class="['nav-item',{active:activeView==='reviews'}]" @click="activeView='reviews'"><span>✓</span>{{ t('navReview') }}<i>03</i></button>
        <button :class="['nav-item',{active:activeView==='resources'}]" @click="activeView='resources'"><span>▤</span>{{ t('navResources') }}<i>04</i></button>
        <button :class="['nav-item',{active:activeView==='compare'}]" @click="activeView='compare'"><span>⇄</span>{{ t('navCompare') }}<i>05</i></button>
        <button :class="['nav-item',{active:activeView==='trace'}]" @click="activeView='trace'"><span>⌇</span>{{ t('navTrace') }}<i>06</i></button>
      </nav>
      <div class="rail-note">
        <span class="pulse"></span>
        <div><b>{{ t('runtimeOnline') }}</b><small>{{ t('runtimeDetail') }}</small></div>
      </div>
      <div class="rail-foot mono">BUILD 3.0.0<br />FOX-SZ-01 / CN</div>
    </aside>

    <main>
      <header class="topbar">
        <div>
          <h1>{{ t('pageTitle') }}</h1>
        </div>
        <div class="system-state">
          <span :class="['status-dot', runtimeReady ? 'ready' : 'offline']"></span>
          <div><small>{{ t('serviceStatus') }}</small><strong>{{ runtimeReady ? t('ready') : t('waitingBackend') }}</strong></div>
          <label class="locale-select">
            <span>{{ t('language') }}</span>
            <select v-model="locale" aria-label="Language"><option value="zh-TW">繁中</option><option value="zh-CN">简中</option><option value="en-US">EN</option></select>
          </label>
          <div class="clock mono">{{ clock }}</div>
        </div>
      </header>

      <template v-if="activeView === 'planning'">
      <section class="hero-grid">
        <form class="panel mission-card" @submit.prevent="startPlan">
          <div class="panel-heading">
            <div><h2>{{ t('createPlan') }}</h2></div>
            <span class="mode-pill">{{ request.data_source === 'mock' ? t('builtInSource') : t('enterpriseSource') }}</span>
          </div>

          <div class="form-grid">
            <label>{{ t('factoryCode') }}<input v-model="request.factory_id" /></label>
            <label>{{ t('workshop') }}<input v-model="request.workshop_id" /></label>
            <label>{{ t('productionDate') }}<input v-model="request.production_date" type="date" /></label>
            <label>{{ t('preferredTeam') }}<select v-model="request.constraints.preferred_team"><option value="">{{ t('autoMatch') }}</option><option>{{ t('teamA') }}</option><option>{{ t('teamB') }}</option></select></label>
          </div>

          <div class="orders-head"><span>{{ t('pendingOrders') }}</span><span class="mono">{{ request.orders.length }} ORDERS / {{ totalQuantity.toLocaleString() }} PCS</span></div>
          <div class="order-list">
            <div v-for="(order, index) in request.orders" :key="order.order_id" class="order-row">
              <span class="order-index mono">{{ String(index + 1).padStart(2, '0') }}</span>
              <label>{{ t('workOrderNo') }}<input v-model="order.order_id" /></label>
              <label>{{ t('productCode') }}<input v-model="order.product_code" /></label>
              <label class="short">{{ t('quantity') }}<input v-model.number="order.quantity" type="number" min="1" /></label>
              <label class="short">{{ t('priority') }}<select v-model.number="order.priority"><option :value="5">{{ t('priority1') }}</option><option :value="4">{{ t('priority2') }}</option><option :value="3">{{ t('priority3') }}</option></select></label>
            </div>
          </div>

          <div class="mission-footer">
            <div class="toggles">
              <label><input v-model="request.demo_mode" type="checkbox" /> {{ t('ruleEngineFirst') }}</label>
              <label><input v-model="request.require_human_review" type="checkbox" /> {{ t('mandatoryReview') }}</label>
              <select v-model="request.llm_provider" :disabled="request.demo_mode" aria-label="LLM Provider"><option value="deepseek">DeepSeek</option><option value="aliyun">Alibaba Cloud</option><option value="openai">OpenAI</option></select>
              <select v-model="request.data_source" :aria-label="t('businessSource')"><option value="mock">{{ t('builtInSource') }}</option><option value="real">{{ t('enterpriseSource') }}</option></select>
            </div>
            <button class="launch" type="submit" :disabled="planning">
              <span>{{ planning ? t('planning') : t('startPlanning') }}</span><b>{{ planning ? progress + '%' : '→' }}</b>
            </button>
          </div>
          <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
        </form>

        <section class="panel flow-card" aria-label="Agent 流程">
          <div class="panel-heading">
            <div><h2>{{ t('agentRail') }}</h2></div>
            <span v-if="traceId" class="trace mono">{{ traceId }}</span>
          </div>
          <div class="production-rail">
            <div v-for="(node, index) in nodes" :key="node.key" :class="['flow-node', nodeStatus(node.key)]">
              <div class="node-track"><span class="node-number mono">{{ String(index + 1).padStart(2, '0') }}</span><i></i></div>
              <div class="node-copy">
                <strong>{{ t(node.labelKey) }}</strong>
                <span>{{ nodeDescription(node.key) }}</span>
              </div>
              <b class="node-state mono">{{ stateText(nodeStatus(node.key)) }}</b>
            </div>
          </div>
          <div class="flow-footer">
            <span><i class="legend completed"></i>{{ t('completed') }}</span><span><i class="legend running"></i>{{ t('running') }}</span><span><i class="legend degraded"></i>{{ t('degraded') }}</span>
            <b class="mono">CHECKPOINT {{ taskVersion ? `V${taskVersion}` : '--' }}</b>
          </div>
        </section>
      </section>

      <section class="telemetry">
        <article><span>{{ t('availableDevices') }}</span><b>{{ deviceCount }}</b><small>{{ t('deviceUnit') }}</small></article>
        <article><span>{{ t('onDuty') }}</span><b>{{ headcount }}</b><small>{{ t('peopleUnit') }}</small></article>
        <article><span>{{ t('averageLoad') }}</span><b>{{ utilization }}<em>%</em></b><small>{{ t('loadNote') }}</small></article>
        <article><span>{{ t('orchestrationTime') }}</span><b>{{ elapsed }}<em>ms</em></b><small>{{ t('timeNote') }}</small></article>
      </section>

      <section v-if="plan" class="result-grid">
        <article class="panel schedule-card">
          <div class="panel-heading">
            <div><h2>{{ t('stationTimeline') }}</h2><small class="plan-reference mono">{{ plan.plan_id }}</small></div>
            <span :class="['approval-pill', taskStatus]">{{ statusLabel }}</span>
          </div>
          <div class="gantt-head mono"><span>{{ t('taskStation') }}</span><div><i>08:00</i><i>12:00</i><i>16:00</i><i>20:00</i><i>24:00</i></div></div>
          <div class="gantt">
            <div v-for="item in plan.assignments" :key="item.assignment_id" class="gantt-row">
              <div class="gantt-label"><b>{{ processLabel(item.process) }} · {{ item.station_code }}</b><small>{{ item.order_id }} / {{ teamLabel(item.team_name) }}</small></div>
              <div class="gantt-track"><span :class="['gantt-bar', processClass(item.process)]" :style="barStyle(item)"><b>{{ item.planned_quantity }} pcs</b><small>{{ shortTime(item.start_at) }}—{{ shortTime(item.end_at) }}</small></span></div>
            </div>
          </div>
        </article>

        <aside class="panel review-card">
          <div class="review-title"><h2>{{ t('supervisorReview') }}</h2><p>{{ t('reviewHelp') }}</p></div>
          <div class="summary-grid">
            <div><span>{{ t('plannedQuantity') }}</span><b>{{ plan.summary.planned_quantity.toLocaleString() }}</b></div>
            <div><span>{{ t('estimatedCompletion') }}</span><b>{{ shortDateTime(plan.summary.estimated_completion_at) }}</b></div>
          </div>
          <div class="risk-list">
            <div v-for="risk in plan.risks" :key="risk.code" :class="['risk', risk.level]"><span>{{ riskLevel(risk.level) }}</span><div><b>{{ riskText(risk.code, 'message') }}</b><small>{{ riskText(risk.code, 'mitigation') }}</small></div></div>
          </div>
          <textarea v-model="reviewComment" rows="3" :placeholder="t('reviewPlaceholder')"></textarea>
          <div class="review-actions">
            <button class="reject" :disabled="reviewing || taskStatus !== 'need_review'" @click="doReview('reject')">{{ t('rejectPlan') }}</button>
            <button class="approve" :disabled="reviewing || taskStatus !== 'need_review'" @click="doReview('approve')">{{ t('approvePublish') }} <span>→</span></button>
          </div>
          <p v-if="taskStatus === 'approved'" class="review-success">✓ {{ t('approvedMessage') }}</p>
          <p v-if="taskStatus === 'rejected'" class="review-rejected">{{ t('rejectedMessage') }}</p>
        </aside>
      </section>
      </template>

      <TaskCenter v-else-if="activeView === 'tasks'" :locale="locale" @open-review="openReview" @open-trace="openTrace" />
      <ReviewCenter v-else-if="activeView === 'reviews'" :locale="locale" :initial-task-id="selectedTaskId" @reviewed="onReviewed" />
      <ResourceCenter v-else-if="activeView === 'resources'" :locale="locale" />
      <PlanCompare v-else-if="activeView === 'compare'" :locale="locale" @open-review="openReview" />
      <TraceCenter v-else :locale="locale" :initial-task-id="selectedTaskId" />

      <footer class="page-foot"><span>{{ t('footer') }}</span><span class="mono">SSE / LANGGRAPH / HITL / MULTI-LLM</span></footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import PlanCompare from '../components/PlanCompare.vue'
import ResourceCenter from '../components/ResourceCenter.vue'
import ReviewCenter from '../components/ReviewCenter.vue'
import TaskCenter from '../components/TaskCenter.vue'
import TraceCenter from '../components/TraceCenter.vue'
import { getRuntime, reviewTask, streamSchedulingPlan } from '../services/api'
import type { Assignment, SchedulingPlan, SchedulingRequest, StreamEvent, TaskSnapshot, TaskStatus } from '../types'

type Locale = 'zh-TW' | 'zh-CN' | 'en-US'
const savedLocale = localStorage.getItem('forgeflow-locale')
const locale = ref<Locale>((['zh-TW', 'zh-CN', 'en-US'].includes(savedLocale || '') ? savedLocale : 'zh-TW') as Locale)
const messages: Record<Locale, Record<string, string>> = {
  'zh-TW': {
    brandSubtitle: '作業規劃中樞', mainNav: '主要功能', navPlanning: '計畫編排', navTasks: '任務中心', navReview: '審核中心', navResources: '資源台帳', navCompare: '版本比較', navTrace: '運行追蹤',
    runtimeOnline: '系統服務在線', runtimeDetail: '業務閘道 · 狀態儲存', pageTitle: '車間多任務作業規劃', serviceStatus: '服務狀態', ready: '全部就緒', waitingBackend: '等待服務', language: '語言',
    createPlan: '建立今日計畫', builtInSource: '計畫資料庫', enterpriseSource: '企業整合資料源', factoryCode: '工廠代碼', workshop: '目標車間', productionDate: '生產日期', preferredTeam: '優先班組', autoMatch: '自動匹配', teamA: '甲班', teamB: '乙班',
    pendingOrders: '待排工單', workOrderNo: '工單號', productCode: '產品料號', quantity: '數量', priority: '優先級', priority1: 'P1 緊急', priority2: 'P2 高', priority3: 'P3 常規', ruleEngineFirst: '規則引擎優先', mandatoryReview: '強制人工審核', businessSource: '業務資料來源', planning: '編排執行中', startPlanning: '啟動智慧排程',
    agentRail: 'Agent 生產軌道', deviceLabel: '設備資源檢索', shiftLabel: '班組排班查詢', assignLabel: '工位任務分配', planLabel: '作業方案產生', reviewLabel: '人工審核', completed: '已完成', running: '執行中', degraded: '安全降級', availableDevices: '可用設備', deviceUnit: '台 / 能力已匹配', onDuty: '當班人數', peopleUnit: '人 / 日夜兩班', averageLoad: '平均負載', loadNote: '約束計算後估算', orchestrationTime: '編排耗時', timeNote: '五節點累計',
    stationTimeline: '工位執行時間軸', taskStation: '任務 / 工位', supervisorReview: '主管覆核', reviewHelp: '計畫不會自動進入產線。確認資源、交期與風險後再下發 MES。', plannedQuantity: '計畫數量', estimatedCompletion: '預計完成', reviewPlaceholder: '填寫審核意見（選填）', rejectPlan: '退回計畫', approvePublish: '核准並下發', approvedMessage: '審核已通過，MES 介面已接收計畫', rejectedMessage: '計畫已退回，未下發產線', footer: 'FORGEFLOW · 製造執行系統智慧編排層',
    statusWaitingReview: '等待審核', statusApproved: '已核准下發', statusRejected: '已退回', statusProcessing: '產生中', statusFailed: '執行失敗', statusPending: '待執行',
    descDevice: '接入設備台帳與即時狀態', descShift: '校驗到崗與技能約束', descAssign: '按製程能力計算負載', descPlan: '規則底座與風險建議', descReview: '保存檢查點並等待主管', doneDevice: '設備資源檢索完成', doneShift: '班組與工單資料已就緒', doneAssign: '工位任務分配完成', donePlan: '作業方案已產生', doneReview: '方案已進入人工審核',
    processAssembly: '組裝', processTest: '測試', processPackage: '包裝', riskLow: '低', riskMedium: '中', riskHigh: '高', riskNormal: '資源與交期約束均在安全區間', mitigationNormal: '依標準班前點檢執行', riskData: '部分業務資料不可用，已套用安全基線資源', mitigationData: '主管確認設備與班組後再下發', riskCapacity: '至少一個工位負載超過單班額定產能', mitigationCapacity: '拆分批次至夜班或啟用跨線生產', riskAttendance: '夜班到崗率低於 90%', mitigationAttendance: '預留 2 名多能工並於班前確認到崗',
  },
  'zh-CN': {
    brandSubtitle: '作业规划中枢', mainNav: '主要功能', navPlanning: '计划编排', navTasks: '任务中心', navReview: '审核中心', navResources: '资源台账', navCompare: '版本对比', navTrace: '运行追踪',
    runtimeOnline: '系统服务在线', runtimeDetail: '业务网关 · 状态存储', pageTitle: '车间多任务作业规划', serviceStatus: '服务状态', ready: '全部就绪', waitingBackend: '等待服务', language: '语言',
    createPlan: '创建今日计划', builtInSource: '计划数据库', enterpriseSource: '企业集成数据源', factoryCode: '工厂编码', workshop: '目标车间', productionDate: '生产日期', preferredTeam: '优先班组', autoMatch: '自动匹配', teamA: '甲班', teamB: '乙班',
    pendingOrders: '待排工单', workOrderNo: '工单号', productCode: '产品料号', quantity: '数量', priority: '优先级', priority1: 'P1 紧急', priority2: 'P2 高', priority3: 'P3 常规', ruleEngineFirst: '规则引擎优先', mandatoryReview: '强制人工审核', businessSource: '业务数据来源', planning: '编排执行中', startPlanning: '启动智能排产',
    agentRail: 'Agent 生产轨道', deviceLabel: '设备资源检索', shiftLabel: '班组排班查询', assignLabel: '工位任务分配', planLabel: '作业方案生成', reviewLabel: '人工审核', completed: '已完成', running: '执行中', degraded: '安全降级', availableDevices: '可用设备', deviceUnit: '台 / 能力已匹配', onDuty: '当班人数', peopleUnit: '人 / 日夜两班', averageLoad: '平均负载', loadNote: '约束计算后估算', orchestrationTime: '编排耗时', timeNote: '五节点累计',
    stationTimeline: '工位执行时间轴', taskStation: '任务 / 工位', supervisorReview: '主管复核', reviewHelp: '计划不会自动进入产线。确认资源、交期与风险后再下发 MES。', plannedQuantity: '计划数量', estimatedCompletion: '预计完成', reviewPlaceholder: '填写审核意见（选填）', rejectPlan: '退回计划', approvePublish: '批准并下发', approvedMessage: '审核已通过，MES 接口已接收计划', rejectedMessage: '计划已退回，未下发产线', footer: 'FORGEFLOW · 制造执行系统智能编排层',
    statusWaitingReview: '等待审核', statusApproved: '已批准下发', statusRejected: '已退回', statusProcessing: '生成中', statusFailed: '执行失败', statusPending: '待执行',
    descDevice: '接入设备台账与实时状态', descShift: '校验到岗与技能约束', descAssign: '按工艺能力计算负载', descPlan: '规则底座与风险建议', descReview: '保存检查点并等待主管', doneDevice: '设备资源检索完成', doneShift: '班组与工单数据已就绪', doneAssign: '工位任务分配完成', donePlan: '作业方案已生成', doneReview: '方案已进入人工审核',
    processAssembly: '组装', processTest: '测试', processPackage: '包装', riskLow: '低', riskMedium: '中', riskHigh: '高', riskNormal: '资源与交期约束均在安全区间', mitigationNormal: '按标准班前点检执行', riskData: '部分业务数据不可用，已使用安全基线资源', mitigationData: '主管确认设备与班组后再下发', riskCapacity: '至少一个工位负载超过单班额定产能', mitigationCapacity: '拆分批次到夜班或启用跨线生产', riskAttendance: '夜班到岗率低于 90%', mitigationAttendance: '预留 2 名多能工并在班前确认到岗',
  },
  'en-US': {
    brandSubtitle: 'Operations Planning Hub', mainNav: 'Primary navigation', navPlanning: 'Planning', navTasks: 'Task Center', navReview: 'Review Center', navResources: 'Resources', navCompare: 'Plan Compare', navTrace: 'Run Trace',
    runtimeOnline: 'Services online', runtimeDetail: 'Business gateway · State store', pageTitle: 'Workshop Multi-Task Planning', serviceStatus: 'Service status', ready: 'All systems ready', waitingBackend: 'Waiting for service', language: 'Language',
    createPlan: 'Create daily plan', builtInSource: 'Planning database', enterpriseSource: 'Enterprise data source', factoryCode: 'Factory code', workshop: 'Workshop', productionDate: 'Production date', preferredTeam: 'Preferred team', autoMatch: 'Auto match', teamA: 'Team A', teamB: 'Team B',
    pendingOrders: 'Orders to schedule', workOrderNo: 'Work order', productCode: 'Product code', quantity: 'Quantity', priority: 'Priority', priority1: 'P1 Critical', priority2: 'P2 High', priority3: 'P3 Normal', ruleEngineFirst: 'Rules engine first', mandatoryReview: 'Mandatory review', businessSource: 'Business data source', planning: 'Planning in progress', startPlanning: 'Start planning',
    agentRail: 'Agent production rail', deviceLabel: 'Equipment retrieval', shiftLabel: 'Shift roster query', assignLabel: 'Station allocation', planLabel: 'Plan generation', reviewLabel: 'Human review', completed: 'Completed', running: 'Running', degraded: 'Safe fallback', availableDevices: 'Available equipment', deviceUnit: 'units / capability matched', onDuty: 'On-duty staff', peopleUnit: 'people / two shifts', averageLoad: 'Average load', loadNote: 'after constraint calculation', orchestrationTime: 'Orchestration time', timeNote: 'five-node total',
    stationTimeline: 'Station execution timeline', taskStation: 'Task / station', supervisorReview: 'Supervisor review', reviewHelp: 'The plan will not reach the line automatically. Verify resources, due dates and risks before publishing to MES.', plannedQuantity: 'Planned quantity', estimatedCompletion: 'Estimated finish', reviewPlaceholder: 'Add a review note (optional)', rejectPlan: 'Return plan', approvePublish: 'Approve & publish', approvedMessage: 'Approved; the MES interface accepted the plan', rejectedMessage: 'Plan returned and not released to production', footer: 'FORGEFLOW · Intelligent orchestration for manufacturing execution',
    statusWaitingReview: 'Awaiting review', statusApproved: 'Approved', statusRejected: 'Returned', statusProcessing: 'Generating', statusFailed: 'Failed', statusPending: 'Pending',
    descDevice: 'Load equipment registry and live status', descShift: 'Validate attendance and skill constraints', descAssign: 'Calculate load by process capability', descPlan: 'Rule baseline and risk recommendations', descReview: 'Persist checkpoint and await supervisor', doneDevice: 'Equipment resources retrieved', doneShift: 'Shift and order data ready', doneAssign: 'Station tasks assigned', donePlan: 'Execution plan generated', doneReview: 'Plan entered supervisor review',
    processAssembly: 'Assembly', processTest: 'Test', processPackage: 'Packaging', riskLow: 'LOW', riskMedium: 'MED', riskHigh: 'HIGH', riskNormal: 'Resources and due-date constraints are within the safe range', mitigationNormal: 'Run the standard pre-shift inspection', riskData: 'Some business data was unavailable; safe baseline resources were applied', mitigationData: 'Verify equipment and shifts before release', riskCapacity: 'At least one station exceeds rated single-shift capacity', mitigationCapacity: 'Split the lot into the night shift or enable cross-line production', riskAttendance: 'Night-shift attendance is below 90%', mitigationAttendance: 'Reserve two multi-skilled operators and confirm attendance before shift',
  },
}
const t = (key: string) => messages[locale.value][key] || key
watch(locale, value => { localStorage.setItem('forgeflow-locale', value); document.documentElement.lang = value }, { immediate: true })

type WorkspaceView = 'planning' | 'tasks' | 'reviews' | 'resources' | 'compare' | 'trace'
const activeView = ref<WorkspaceView>('planning')
const selectedTaskId = ref('')
function openReview(id: string) { selectedTaskId.value = id; activeView.value = 'reviews' }
function openTrace(id: string) { selectedTaskId.value = id; activeView.value = 'trace' }
function onReviewed(task: TaskSnapshot) { if (task.task_id === taskId.value) { taskStatus.value = task.status; taskVersion.value = task.version; plan.value = task.plan || plan.value } }

const nodes = [
  { key: 'device_resource', labelKey: 'deviceLabel', en: 'EQUIPMENT' },
  { key: 'shift_query', labelKey: 'shiftLabel', en: 'WORKFORCE' },
  { key: 'station_assign', labelKey: 'assignLabel', en: 'ALLOCATION' },
  { key: 'plan_generate', labelKey: 'planLabel', en: 'PLANNING' },
  { key: 'human_review', labelKey: 'reviewLabel', en: 'REVIEW' },
]

const request = reactive<SchedulingRequest>({
  task_name: 'DIP 車間日計畫', factory_id: 'FOX-SZ-01', workshop_id: 'DIP-A', production_date: '2026-09-10',
  shift_codes: ['DAY', 'NIGHT'], llm_provider: 'deepseek', data_source: 'mock', demo_mode: true, require_human_review: true,
  constraints: { preferred_team: '', max_overtime_minutes: 60, allow_cross_line: true, notes: '高優工單先行；測試工位預留首件確認時間' },
  orders: [
    { order_id: 'MO-260910-081', product_code: 'MB-A17-PRO', quantity: 1200, priority: 5, due_at: '2026-09-10T20:00:00+08:00', process_route: ['组装', '测试', '包装'], cycle_time_seconds: 42 },
    { order_id: 'MO-260910-096', product_code: 'MB-C08-LITE', quantity: 860, priority: 3, due_at: '2026-09-11T08:00:00+08:00', process_route: ['组装', '测试', '包装'], cycle_time_seconds: 55 },
  ],
})

const planning = ref(false)
const reviewing = ref(false)
const runtimeReady = ref(false)
const clock = ref('')
const taskId = ref('')
const traceId = ref('')
const taskVersion = ref(0)
const taskStatus = ref<TaskStatus>('pending')
const plan = ref<SchedulingPlan | null>(null)
const events = ref<StreamEvent[]>([])
const errorMessage = ref('')
const reviewComment = ref('')
let timer: number | undefined
let abortController: AbortController | undefined

const totalQuantity = computed(() => request.orders.reduce((sum, order) => sum + Number(order.quantity || 0), 0))
const completedNodes = computed(() => new Set(events.value.filter(e => ['completed', 'degraded'].includes(e.status)).map(e => e.node)).size)
const progress = computed(() => Math.min(100, completedNodes.value * 20))
const stepByNode = computed(() => Object.fromEntries(events.value.map(event => [event.node, event])))
const deviceCount = computed(() => Number(stepByNode.value.device_resource?.data?.summary?.available || plan.value?.summary.device_count || 0))
const headcount = computed(() => Number(stepByNode.value.shift_query?.data?.summary?.headcount || 0))
const utilization = computed(() => Math.round((plan.value?.summary.average_utilization || 0) * 100))
const elapsed = computed(() => Math.max(0, ...events.value.map(event => (event.steps || []).reduce((sum, step) => sum + Number(step.duration_ms || 0), 0))))
const statusLabel = computed(() => ({ need_review: t('statusWaitingReview'), approved: t('statusApproved'), rejected: t('statusRejected'), processing: t('statusProcessing'), failed: t('statusFailed'), pending: t('statusPending') }[taskStatus.value]))

function nodeStatus(key: string) {
  const event = stepByNode.value[key]
  if (event) return event.status
  const runningIndex = planning.value ? completedNodes.value : -1
  return nodes[runningIndex]?.key === key ? 'running' : 'waiting'
}
function stateText(state: string) { return ({ waiting: 'WAIT', running: 'RUN', completed: 'DONE', degraded: 'SAFE' } as Record<string, string>)[state] || state.toUpperCase() }
function nodeDescription(key: string) {
  const event = stepByNode.value[key]
  const pendingKey = ({ device_resource: 'descDevice', shift_query: 'descShift', station_assign: 'descAssign', plan_generate: 'descPlan', human_review: 'descReview' } as Record<string, string>)[key]
  const doneKey = ({ device_resource: 'doneDevice', shift_query: 'doneShift', station_assign: 'doneAssign', plan_generate: 'donePlan', human_review: 'doneReview' } as Record<string, string>)[key]
  return t(event ? doneKey : pendingKey)
}
function shortTime(value: string) { return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }) }
function shortDateTime(value: string) { return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) }
function processClass(process: string) { return process === '组装' ? 'assembly' : process === '测试' ? 'test' : 'package' }
function processLabel(process: string) { return process === '组装' ? t('processAssembly') : process === '测试' ? t('processTest') : t('processPackage') }
function teamLabel(team: string) { return locale.value === 'en-US' ? (team === '甲班' ? 'Team A' : team === '乙班' ? 'Team B' : team) : team }
function riskLevel(level: string) { return t(level === 'high' ? 'riskHigh' : level === 'medium' ? 'riskMedium' : 'riskLow') }
function riskText(code: string, field: 'message' | 'mitigation') {
  const keys: Record<string, [string, string]> = {
    NORMAL: ['riskNormal', 'mitigationNormal'], DATA_DEGRADED: ['riskData', 'mitigationData'], CAPACITY_OVERLOAD: ['riskCapacity', 'mitigationCapacity'], ATTENDANCE_LOW: ['riskAttendance', 'mitigationAttendance'],
  }
  const pair = keys[code]
  return pair ? t(pair[field === 'message' ? 0 : 1]) : code
}
function barStyle(item: Assignment) {
  const startHour = new Date(item.start_at).getHours() + new Date(item.start_at).getMinutes() / 60
  const end = new Date(item.end_at)
  let endHour = end.getHours() + end.getMinutes() / 60
  if (new Date(item.end_at).getDate() !== new Date(item.start_at).getDate()) endHour += 24
  return { left: `${Math.max(0, ((startHour - 8) / 20) * 100)}%`, width: `${Math.max(8, ((endHour - startHour) / 20) * 100)}%` }
}

async function startPlan() {
  abortController?.abort()
  abortController = new AbortController()
  planning.value = true; errorMessage.value = ''; events.value = []; plan.value = null; taskStatus.value = 'processing'; taskVersion.value = 0
  try {
    await streamSchedulingPlan(request, (event) => {
      taskId.value = event.task_id || taskId.value
      traceId.value = event.trace_id || traceId.value
      if (!['init', 'complete'].includes(event.node)) events.value = [...events.value.filter(e => e.node !== event.node), event]
      if (event.data?.plan) plan.value = event.data.plan as SchedulingPlan
      if (event.data?.version) taskVersion.value = Number(event.data.version)
      if (event.data?.task_status) taskStatus.value = event.data.task_status as TaskStatus
      if (event.node === 'complete' && event.data) {
        taskStatus.value = event.data.status as TaskStatus
        taskVersion.value = Number(event.data.version)
        if (event.data.plan) plan.value = event.data.plan as SchedulingPlan
      }
      if (event.node === 'error') throw new Error(event.message)
    }, abortController.signal)
  } catch (error: any) {
    if (error?.name !== 'AbortError') errorMessage.value = error?.message || '规划执行失败，请检查后端服务'
  } finally { planning.value = false }
}

async function doReview(action: 'approve' | 'reject') {
  if (!taskId.value) return
  reviewing.value = true; errorMessage.value = ''
  try {
    const snapshot = await reviewTask(taskId.value, action, taskVersion.value, reviewComment.value)
    taskStatus.value = snapshot.status; taskVersion.value = snapshot.version; plan.value = snapshot.plan || plan.value
  } catch (error: any) { errorMessage.value = error?.message || t('statusFailed') }
  finally { reviewing.value = false }
}

onMounted(async () => {
  const tick = () => { clock.value = new Date().toLocaleTimeString(locale.value, { hour12: false }) }
  tick(); timer = window.setInterval(tick, 1000)
  try { await getRuntime(); runtimeReady.value = true } catch { runtimeReady.value = false }
})
onBeforeUnmount(() => { if (timer) clearInterval(timer); abortController?.abort() })
</script>

<style scoped>
.shell { min-height: 100vh; display: grid; grid-template-columns: 224px 1fr; position: relative; }
.rail { position: sticky; top: 0; height: 100vh; padding: 28px 18px 20px; border-right: 1px solid rgba(145,160,163,.18); background: rgba(9,15,18,.95); display: flex; flex-direction: column; z-index: 2; }
.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 30px; border-bottom: 1px solid rgba(145,160,163,.18); }
.brand strong { display: block; font: 700 18px/1 "Bahnschrift", sans-serif; letter-spacing: .08em; }.brand small { color: var(--muted); font-size: 11px; letter-spacing: .12em; }
.brand-mark { width: 36px; height: 36px; display: flex; align-items: end; gap: 3px; padding: 7px; background: var(--safety); clip-path: polygon(0 0, 78% 0, 100% 22%, 100% 100%, 0 100%); }
.brand-mark span { width: 5px; background: var(--iron); }.brand-mark span:nth-child(1){height:11px}.brand-mark span:nth-child(2){height:20px}.brand-mark span:nth-child(3){height:15px}
nav { display: grid; gap: 6px; padding-top: 26px; }.nav-item { border: 0; color: var(--muted); background: transparent; display: grid; grid-template-columns: 24px 1fr auto; gap: 8px; align-items: center; text-align: left; padding: 13px 12px; font-size: 13px; border-left: 2px solid transparent; }.nav-item i { font: normal 10px "Cascadia Mono"; opacity: .45; }.nav-item.active { color: var(--paper); background: linear-gradient(90deg, rgba(88,196,214,.12), transparent); border-left-color: var(--coolant); }.nav-item.active span{color:var(--coolant)}
.rail-note { margin-top: auto; display: flex; gap: 10px; padding: 13px 10px; border: 1px solid rgba(117,198,154,.18); background: rgba(117,198,154,.05); }.rail-note b,.rail-note small{display:block}.rail-note b{font-size:11px}.rail-note small{font-size:9px;color:var(--muted);margin-top:3px}.pulse{width:7px;height:7px;background:var(--ok);border-radius:50%;box-shadow:0 0 0 5px rgba(117,198,154,.1);margin-top:4px}.rail-foot{color:#536268;font-size:9px;line-height:1.7;margin:18px 8px 0}
main { min-width: 0; padding: 28px 34px 18px; max-width: 1700px; width: 100%; margin: 0 auto; }.topbar{display:flex;justify-content:space-between;align-items:end;margin-bottom:24px}.topbar h1{font:600 30px/1.15 "Bahnschrift",sans-serif;margin:6px 0 0;letter-spacing:.04em}.system-state{display:flex;align-items:center;gap:11px}.system-state small,.system-state strong{display:block}.system-state small{font-size:10px;color:var(--muted)}.system-state strong{font-size:12px}.status-dot{width:8px;height:8px;border-radius:50%}.status-dot.ready{background:var(--ok);box-shadow:0 0 0 5px rgba(117,198,154,.1)}.status-dot.offline{background:var(--oxide)}.clock{margin-left:16px;padding-left:18px;border-left:1px solid var(--steel);font-size:18px;color:var(--coolant)}.locale-select{display:flex;align-items:center;gap:7px;margin-left:12px;padding-left:14px;border-left:1px solid var(--steel)}.locale-select span{font-size:9px;color:var(--muted);letter-spacing:.08em}.locale-select select{background:#0e171b;color:var(--paper);border:1px solid var(--steel);padding:7px 22px 7px 8px;font:10px "Cascadia Mono",Consolas,monospace}
.hero-grid{display:grid;grid-template-columns:minmax(630px,1.42fr) minmax(350px,.78fr);gap:16px}.mission-card,.flow-card,.schedule-card,.review-card{clip-path:polygon(0 0,calc(100% - 16px) 0,100% 16px,100% 100%,0 100%)}.mission-card,.flow-card{padding:22px}.panel-heading{display:flex;align-items:start;justify-content:space-between;gap:16px;margin-bottom:20px}.panel-heading h2,.review-title h2{font:600 19px "Bahnschrift",sans-serif;margin:5px 0 0}.mode-pill,.trace,.approval-pill{font-size:10px;border:1px solid rgba(88,196,214,.28);color:var(--coolant);padding:6px 9px;background:rgba(88,196,214,.06)}
.plan-reference{display:block;margin-top:5px;color:#617177;font-size:9px;letter-spacing:.06em}
.form-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.form-grid label,.order-row label{color:var(--muted);font-size:10px}.form-grid input,.form-grid select,.order-row input,.order-row select,.toggles select,textarea{width:100%;margin-top:6px;background:#0e171b;color:var(--paper);border:1px solid var(--steel);padding:9px 10px;border-radius:0}.form-grid input:hover,.form-grid select:hover,.order-row input:hover,.order-row select:hover,textarea:hover{border-color:#42585f}.orders-head{display:flex;justify-content:space-between;margin:22px 0 8px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}.order-list{border-top:1px solid var(--steel)}.order-row{display:grid;grid-template-columns:28px 1fr 1fr .62fr .72fr;gap:10px;align-items:end;padding:10px 0;border-bottom:1px solid rgba(38,52,58,.7)}.order-index{color:var(--safety);padding:10px 0}.mission-footer{display:flex;justify-content:space-between;gap:14px;align-items:end;margin-top:16px}.toggles{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.toggles label{font-size:10px;color:var(--muted);display:flex;gap:5px;align-items:center}.toggles input{accent-color:var(--coolant)}.toggles select{width:auto;margin:0;font-size:10px;padding:8px}.launch{min-width:190px;border:0;color:#101619;background:var(--safety);display:flex;justify-content:space-between;padding:13px 15px;font-weight:700;clip-path:polygon(0 0,calc(100% - 10px) 0,100% 10px,100% 100%,0 100%)}.launch:hover{background:#ffc15d}.launch:disabled{cursor:wait;opacity:.72}.error-banner{background:rgba(197,90,61,.12);border-left:3px solid var(--oxide);padding:10px;color:#f4a38e;font-size:11px;margin:12px 0 0}
.production-rail{position:relative}.production-rail::before{content:"";position:absolute;left:16px;top:20px;bottom:22px;width:1px;background:var(--steel)}.flow-node{position:relative;display:grid;grid-template-columns:34px 1fr auto;gap:13px;min-height:70px}.node-track{z-index:1}.node-number{display:grid;place-items:center;width:33px;height:33px;border:1px solid var(--steel);background:var(--gunmetal);color:#607177;font-size:9px}.flow-node.completed .node-number{border-color:var(--coolant);color:var(--coolant);background:#11272b}.flow-node.running .node-number{border-color:var(--safety);color:var(--safety);box-shadow:0 0 0 5px rgba(245,166,35,.08);animation:signal 1.2s ease-in-out infinite}.flow-node.degraded .node-number{border-color:var(--oxide);color:#ef896e}.node-copy small,.node-copy strong,.node-copy span{display:block}.node-copy small{color:#617177;font:9px "Cascadia Mono";letter-spacing:.12em}.node-copy strong{font-size:13px;margin:3px 0}.node-copy span{color:var(--muted);font-size:10px}.node-state{font:9px "Cascadia Mono";color:#536268;margin-top:8px}.completed .node-state{color:var(--coolant)}.running .node-state{color:var(--safety)}.degraded .node-state{color:var(--oxide)}.flow-footer{display:flex;gap:14px;align-items:center;padding-top:12px;border-top:1px solid var(--steel);font-size:9px;color:var(--muted)}.flow-footer span{display:flex;align-items:center;gap:5px}.flow-footer b{margin-left:auto;color:#617177}.legend{width:5px;height:5px;border-radius:50%;background:#45545a}.legend.completed{background:var(--coolant)}.legend.running{background:var(--safety)}.legend.degraded{background:var(--oxide)}
.telemetry{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin:16px 0;background:var(--steel);border:1px solid var(--steel)}.telemetry article{background:#111a1e;padding:15px 18px;display:grid;grid-template-columns:1fr auto;align-items:end}.telemetry span{color:var(--muted);font-size:10px}.telemetry b{grid-row:1/3;grid-column:2;font:600 26px "Bahnschrift";color:var(--paper)}.telemetry b em{font:normal 11px "Cascadia Mono";color:var(--coolant);margin-left:3px}.telemetry small{font-size:9px;color:#59696e;margin-top:4px}
.result-grid{display:grid;grid-template-columns:minmax(650px,1.5fr) minmax(320px,.5fr);gap:16px}.schedule-card,.review-card{padding:22px}.approval-pill.need_review{color:var(--safety);border-color:rgba(245,166,35,.3);background:rgba(245,166,35,.08)}.approval-pill.approved{color:var(--ok);border-color:rgba(117,198,154,.3)}.approval-pill.rejected{color:#ef896e;border-color:rgba(197,90,61,.3)}.gantt-head{display:grid;grid-template-columns:190px 1fr;color:#607177;font-size:9px;padding-bottom:9px;border-bottom:1px solid var(--steel)}.gantt-head div{display:flex;justify-content:space-between}.gantt-head i{font-style:normal}.gantt-row{display:grid;grid-template-columns:190px 1fr;min-height:55px;border-bottom:1px solid rgba(38,52,58,.62);align-items:center}.gantt-label b,.gantt-label small{display:block}.gantt-label b{font-size:11px}.gantt-label small{color:var(--muted);font-size:9px;margin-top:3px}.gantt-track{position:relative;height:29px;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(25% - 1px),rgba(145,160,163,.08) calc(25% - 1px),rgba(145,160,163,.08) 25%)}.gantt-bar{position:absolute;top:2px;height:25px;min-width:65px;padding:4px 7px;color:#081114;overflow:hidden;white-space:nowrap}.gantt-bar b,.gantt-bar small{font-size:8px;display:block}.gantt-bar small{opacity:.7}.gantt-bar.assembly{background:var(--coolant)}.gantt-bar.test{background:var(--safety)}.gantt-bar.package{background:var(--ok)}
.review-title{padding-bottom:17px;border-bottom:1px solid var(--steel)}.review-title p{font-size:11px;line-height:1.6;color:var(--muted);margin:10px 0 0}.summary-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--steel);margin:15px 0}.summary-grid div{background:#10191d;padding:11px}.summary-grid span,.summary-grid b{display:block}.summary-grid span{font-size:9px;color:var(--muted)}.summary-grid b{font:600 14px "Bahnschrift";margin-top:4px}.risk-list{display:grid;gap:8px;margin-bottom:14px}.risk{display:grid;grid-template-columns:50px 1fr;gap:8px;padding:10px;background:#10191d;border-left:2px solid var(--coolant)}.risk.medium{border-color:var(--safety)}.risk.high{border-color:var(--oxide)}.risk>span{font:8px "Cascadia Mono";color:var(--safety)}.risk b,.risk small{display:block}.risk b{font-size:10px}.risk small{font-size:9px;color:var(--muted);line-height:1.45;margin-top:4px}textarea{resize:vertical;min-height:65px;font-size:10px}.review-actions{display:grid;grid-template-columns:.7fr 1.3fr;gap:8px;margin-top:10px}.review-actions button{border:1px solid var(--steel);padding:11px;background:transparent;color:var(--muted);font-size:11px}.review-actions .approve{border:0;background:var(--coolant);color:#081114;font-weight:700;display:flex;justify-content:space-between}.review-actions button:disabled{opacity:.35;cursor:not-allowed}.review-success,.review-rejected{font-size:10px;padding:10px;margin:10px 0 0}.review-success{color:var(--ok);background:rgba(117,198,154,.08)}.review-rejected{color:#ef896e;background:rgba(197,90,61,.08)}
.page-foot{display:flex;justify-content:space-between;color:#536268;font-size:9px;padding:20px 2px 0}.page-foot span:last-child{letter-spacing:.1em}@keyframes signal{50%{box-shadow:0 0 0 9px rgba(245,166,35,0)}}
@media(max-width:1150px){.shell{grid-template-columns:72px 1fr}.rail{padding:25px 10px}.brand>div:last-child,.nav-item:not(.active){font-size:0}.brand{padding-left:7px}.brand-mark{min-width:36px}.nav-item{grid-template-columns:24px}.nav-item i,.nav-item:not(.active) i,.rail-note div,.rail-foot{display:none}.hero-grid,.result-grid{grid-template-columns:1fr}.flow-card{order:-1}.production-rail{display:grid;grid-template-columns:repeat(5,1fr)}.production-rail::before{left:4%;right:4%;top:16px;bottom:auto;width:auto;height:1px}.flow-node{display:block;min-height:120px}.node-copy{margin-top:8px}.node-state{position:absolute;top:0;right:8px}.flow-footer{grid-column:1/-1}}
@media(max-width:760px){.shell{display:block}.rail{position:static;width:100%;height:auto;flex-direction:row;align-items:center;border-right:0;border-bottom:1px solid var(--steel)}.brand{border:0;padding:0}.rail nav,.rail-note{display:none}main{padding:20px 14px}.topbar{align-items:start}.system-state>div:not(.clock),.status-dot{display:none}.topbar h1{font-size:23px}.hero-grid{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr 1fr}.order-row{grid-template-columns:22px 1fr 1fr}.order-row .short{grid-row:2}.mission-footer{display:block}.launch{width:100%;margin-top:14px}.production-rail{grid-template-columns:1fr}.production-rail::before{left:16px;top:0;bottom:0;width:1px;height:auto}.flow-node{display:grid;min-height:70px}.telemetry{grid-template-columns:1fr 1fr}.result-grid{grid-template-columns:1fr}.gantt-head,.gantt-row{grid-template-columns:130px 1fr}.page-foot{display:none}}
</style>
