<template>
  <section class="workspace-view">
    <div class="workbench-head">
      <div><h2>{{ tx.title }}</h2><p>{{ tx.subtitle }}</p></div>
      <button class="refresh" :disabled="loading" @click="load">↻ {{ tx.refresh }}</button>
    </div>

    <div class="task-kpis">
      <article><span>{{ tx.total }}</span><b>{{ tasks.length }}</b></article>
      <article><span>{{ tx.waiting }}</span><b>{{ waitingCount }}</b></article>
      <article><span>{{ tx.approved }}</span><b>{{ approvedCount }}</b></article>
      <article><span>{{ tx.completion }}</span><b>{{ completionRate }}<small>%</small></b></article>
    </div>

    <div class="task-layout">
      <article class="panel table-panel">
        <div class="table-tools">
          <input v-model="keyword" :placeholder="tx.search" />
          <select v-model="statusFilter"><option value="">{{ tx.allStatuses }}</option><option value="need_review">{{ statusText(locale, 'need_review') }}</option><option value="approved">{{ statusText(locale, 'approved') }}</option><option value="rejected">{{ statusText(locale, 'rejected') }}</option><option value="failed">{{ statusText(locale, 'failed') }}</option></select>
        </div>
        <div class="task-table" role="table">
          <div class="table-row table-header" role="row"><span>{{ tx.task }}</span><span>{{ tx.workshop }}</span><span>{{ tx.productionDate }}</span><span>{{ tx.quantity }}</span><span>{{ tx.updated }}</span><span>{{ tx.status }}</span></div>
          <button v-for="task in filteredTasks" :key="task.task_id" :class="['table-row', { selected: selected?.task_id === task.task_id }]" role="row" @click="selected = task">
            <span><b>{{ task.request.task_name }}</b><small class="mono">{{ task.task_id }}</small></span>
            <span>{{ task.request.workshop_id }}</span><span>{{ task.request.production_date }}</span><span>{{ formatNumber(locale, task.plan?.summary.planned_quantity || 0) }}</span><span>{{ formatDateTime(locale, task.updated_at) }}</span><span><i :class="['status-mark', task.status]"></i>{{ statusText(locale, task.status) }}</span>
          </button>
          <div v-if="!loading && !filteredTasks.length" class="empty">{{ tx.empty }}</div>
          <div v-if="loading" class="empty">{{ tx.loading }}</div>
        </div>
      </article>

      <aside class="panel detail-panel">
        <template v-if="selected">
          <div class="detail-head"><div><h3>{{ selected.request.task_name }}</h3><small class="mono">V{{ selected.version }} · {{ selected.trace_id }}</small></div><span :class="['status-pill', selected.status]">{{ statusText(locale, selected.status) }}</span></div>
          <dl><div><dt>{{ tx.orders }}</dt><dd>{{ selected.plan?.summary.order_count || selected.request.orders.length }}</dd></div><div><dt>{{ tx.devices }}</dt><dd>{{ selected.plan?.summary.device_count || 0 }}</dd></div><div><dt>{{ tx.teams }}</dt><dd>{{ selected.plan?.summary.team_count || 0 }}</dd></div><div><dt>{{ tx.steps }}</dt><dd>{{ selected.steps.length }}/5</dd></div></dl>
          <div class="detail-section"><h4>{{ tx.constraints }}</h4><p>{{ selected.request.constraints.notes || tx.noNotes }}</p><div class="tags"><span>{{ tx.overtime }} {{ selected.request.constraints.max_overtime_minutes }} min</span><span>{{ selected.request.constraints.allow_cross_line ? tx.crossLine : tx.singleLine }}</span></div></div>
          <div class="detail-section"><h4>{{ tx.execution }}</h4><div class="mini-step" v-for="step in selected.steps" :key="step.node"><i :class="step.status"></i><span>{{ nodeLabel(step.node, step.label) }}</span><b class="mono">{{ step.duration_ms || 0 }} ms</b></div></div>
          <div class="detail-actions"><button v-if="selected.status === 'need_review'" class="primary" @click="$emit('open-review', selected.task_id)">{{ tx.review }}</button><button @click="$emit('open-trace', selected.task_id)">{{ tx.trace }}</button></div>
        </template>
        <div v-else class="empty detail-empty">{{ tx.selectTask }}</div>
      </aside>
    </div>
    <p v-if="error" class="error-line">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listTasks } from '../services/api'
import type { TaskSnapshot, TaskStatus } from '../types'
import { formatDateTime, formatNumber, statusText, type Locale } from '../utils/workbench'

const props = defineProps<{ locale: Locale }>()
defineEmits<{ (event: 'open-review', taskId: string): void; (event: 'open-trace', taskId: string): void }>()
const tasks = ref<TaskSnapshot[]>([]), selected = ref<TaskSnapshot | null>(null), loading = ref(false), error = ref(''), keyword = ref(''), statusFilter = ref('')
const copy = {
  'zh-TW': { title:'任務中心',subtitle:'集中管理排程任務、執行狀態與下發結果。',refresh:'重新整理',total:'全部任務',waiting:'待審核',approved:'已核准',completion:'核准率',search:'搜尋任務名稱、工單或 Task ID',allStatuses:'全部狀態',task:'任務',workshop:'車間',productionDate:'生產日期',quantity:'計畫數量',updated:'最後更新',status:'狀態',empty:'尚無符合條件的任務',loading:'正在讀取任務…',orders:'工單',devices:'設備',teams:'班組',steps:'節點',constraints:'排程約束',noNotes:'未填寫額外約束',overtime:'加班上限',crossLine:'允許跨線',singleLine:'限制單線',execution:'執行概況',review:'進入審核',trace:'查看追蹤',selectTask:'請選擇任務查看詳情' },
  'zh-CN': { title:'任务中心',subtitle:'集中管理排程任务、执行状态与下发结果。',refresh:'刷新',total:'全部任务',waiting:'待审核',approved:'已批准',completion:'批准率',search:'搜索任务名称、工单或 Task ID',allStatuses:'全部状态',task:'任务',workshop:'车间',productionDate:'生产日期',quantity:'计划数量',updated:'最后更新',status:'状态',empty:'暂无符合条件的任务',loading:'正在读取任务…',orders:'工单',devices:'设备',teams:'班组',steps:'节点',constraints:'排程约束',noNotes:'未填写额外约束',overtime:'加班上限',crossLine:'允许跨线',singleLine:'限制单线',execution:'执行概况',review:'进入审核',trace:'查看追踪',selectTask:'请选择任务查看详情' },
  'en-US': { title:'Task center',subtitle:'Manage planning jobs, execution status and release results.',refresh:'Refresh',total:'All tasks',waiting:'Awaiting review',approved:'Approved',completion:'Approval rate',search:'Search name, order or Task ID',allStatuses:'All statuses',task:'Task',workshop:'Workshop',productionDate:'Production date',quantity:'Quantity',updated:'Last updated',status:'Status',empty:'No tasks match the current filters',loading:'Loading tasks…',orders:'Orders',devices:'Equipment',teams:'Teams',steps:'Nodes',constraints:'Planning constraints',noNotes:'No additional constraints',overtime:'Overtime limit',crossLine:'Cross-line allowed',singleLine:'Single line only',execution:'Execution overview',review:'Open review',trace:'View trace',selectTask:'Select a task to view details' },
}
const tx = computed(() => copy[props.locale])
const waitingCount = computed(() => tasks.value.filter(t => t.status === 'need_review').length)
const approvedCount = computed(() => tasks.value.filter(t => t.status === 'approved').length)
const completionRate = computed(() => tasks.value.length ? Math.round(approvedCount.value / tasks.value.length * 100) : 0)
const filteredTasks = computed(() => tasks.value.filter(task => {
  const haystack = `${task.task_id} ${task.request.task_name} ${task.request.orders.map(o => o.order_id).join(' ')}`.toLowerCase()
  return (!statusFilter.value || task.status === statusFilter.value as TaskStatus) && haystack.includes(keyword.value.toLowerCase())
}))
const nodeNames:Record<string,[string,string,string]>={device_resource:['設備資源檢索','设备资源检索','Equipment retrieval'],shift_query:['班組排班查詢','班组排班查询','Shift roster query'],station_assign:['工位任務分配','工位任务分配','Station allocation'],plan_generate:['作業方案產生','作业方案生成','Plan generation'],human_review:['人工審核','人工审核','Human review']}
function nodeLabel(node:string,fallback:string){const index=props.locale==='zh-TW'?0:props.locale==='zh-CN'?1:2;return nodeNames[node]?.[index]||fallback}
async function load() { loading.value=true;error.value='';try{tasks.value=await listTasks();selected.value=selected.value ? tasks.value.find(t=>t.task_id===selected.value?.task_id)||tasks.value[0]||null : tasks.value[0]||null}catch(e:any){error.value=e.message}finally{loading.value=false} }
onMounted(load)
</script>

<style scoped>
.workspace-view{display:grid;gap:16px}.workbench-head{display:flex;justify-content:space-between;align-items:end}.workbench-head h2{font:600 25px "Bahnschrift";margin:0}.workbench-head p{color:var(--muted);font-size:11px;margin:6px 0 0}.refresh,.detail-actions button{background:#111a1e;color:var(--paper);border:1px solid var(--steel);padding:10px 14px}.task-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;border:1px solid var(--steel);background:var(--steel)}.task-kpis article{background:#111a1e;padding:15px 18px;display:flex;justify-content:space-between;align-items:end}.task-kpis span{font-size:10px;color:var(--muted)}.task-kpis b{font:600 25px "Bahnschrift"}.task-kpis small{font-size:10px;color:var(--coolant)}.task-layout{display:grid;grid-template-columns:minmax(720px,1.5fr) minmax(300px,.5fr);gap:16px}.table-panel,.detail-panel{padding:18px;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 14px,100% 100%,0 100%)}.table-tools{display:flex;gap:8px;margin-bottom:14px}.table-tools input{flex:1}.table-tools input,.table-tools select{background:#0e171b;color:var(--paper);border:1px solid var(--steel);padding:9px 10px}.task-table{display:grid}.table-row{display:grid;grid-template-columns:2fr .65fr .8fr .65fr .9fr .8fr;gap:12px;align-items:center;min-height:54px;padding:8px 10px;border:0;border-bottom:1px solid rgba(38,52,58,.7);background:transparent;color:var(--paper);text-align:left}.table-row:not(.table-header):hover,.table-row.selected{background:rgba(88,196,214,.06)}.table-row.selected{box-shadow:inset 2px 0 var(--coolant)}.table-header{min-height:34px;color:#69787d;font-size:9px;text-transform:uppercase}.table-row span{font-size:10px}.table-row b,.table-row small{display:block}.table-row b{font-size:11px}.table-row small{color:#607177;font-size:8px;margin-top:4px}.status-mark{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:#68777b}.status-mark.need_review{background:var(--safety)}.status-mark.approved{background:var(--ok)}.status-mark.rejected,.status-mark.failed{background:var(--oxide)}.detail-head{display:flex;justify-content:space-between;gap:10px;padding-bottom:15px;border-bottom:1px solid var(--steel)}.detail-head h3{font-size:15px;margin:0}.detail-head small{display:block;color:#617177;margin-top:5px;font-size:8px}.status-pill{align-self:start;border:1px solid var(--steel);padding:5px 8px;font-size:9px}.status-pill.need_review{color:var(--safety);border-color:rgba(245,166,35,.35)}.status-pill.approved{color:var(--ok);border-color:rgba(117,198,154,.35)}dl{display:grid;grid-template-columns:repeat(4,1fr);margin:14px 0;background:var(--steel);gap:1px}dl div{background:#10191d;padding:10px}dt{font-size:8px;color:var(--muted)}dd{margin:4px 0 0;font:600 15px "Bahnschrift"}.detail-section{padding:12px 0;border-top:1px solid rgba(38,52,58,.7)}.detail-section h4{font-size:10px;color:var(--muted);margin:0 0 8px}.detail-section p{font-size:10px;line-height:1.6;margin:0}.tags{display:flex;gap:6px;margin-top:8px}.tags span{font-size:8px;padding:4px 6px;border:1px solid var(--steel);color:#839297}.mini-step{display:grid;grid-template-columns:9px 1fr auto;gap:7px;align-items:center;padding:5px 0;font-size:9px}.mini-step i{width:5px;height:5px;border-radius:50%;background:var(--ok)}.mini-step i.degraded{background:var(--oxide)}.mini-step b{color:#617177;font-size:8px}.detail-actions{display:flex;gap:8px;margin-top:12px}.detail-actions .primary{background:var(--coolant);border-color:var(--coolant);color:#071115;font-weight:700}.empty{padding:40px;text-align:center;color:#66767b;font-size:11px}.detail-empty{padding-top:100px}.error-line{color:#ef896e;font-size:10px}.mono{font-family:"Cascadia Mono",Consolas,monospace}@media(max-width:1050px){.task-layout{grid-template-columns:1fr}.task-table{overflow:auto}.table-row{min-width:760px}}@media(max-width:700px){.task-kpis{grid-template-columns:1fr 1fr}.workbench-head{align-items:start}.table-panel{overflow:hidden}}
</style>
