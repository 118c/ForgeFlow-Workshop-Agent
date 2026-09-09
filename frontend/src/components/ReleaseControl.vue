<template>
  <section class="ops-page">
    <header class="ops-head"><div><h2>{{ tx.title }}</h2><p>{{ tx.subtitle }}</p></div><span class="scope">{{ workshopId }}</span></header>
    <div class="ops-grid">
      <article class="ops-card">
        <div class="card-title"><div><h3>{{ tx.rollout }}</h3><p>{{ tx.rolloutHint }}</p></div><b v-if="policy">V{{ policy.version }}</b></div>
        <label>{{ tx.workshop }}<input v-model="workshopId" @change="loadPolicy" /></label>
        <div class="mode-grid">
          <button v-for="item in modes" :key="item.value" :class="{active:mode===item.value}" @click="mode=item.value"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></button>
        </div>
        <label v-if="mode==='canary'">{{ tx.traffic }}<input v-model.number="traffic" type="range" min="1" max="99" /><b>{{ traffic }}%</b></label>
        <label>{{ tx.reason }}<input v-model="reason" :placeholder="tx.reasonHint" /></label>
        <div class="actions"><button class="secondary" :disabled="busy || !policy || policy.version < 2" @click="rollback">{{ tx.rollback }}</button><button class="primary" :disabled="busy" @click="save">{{ tx.save }}</button></div>
        <p v-if="notice" class="notice">{{ notice }}</p>
      </article>

      <article class="ops-card">
        <div class="card-title"><div><h3>{{ tx.replay }}</h3><p>{{ tx.replayHint }}</p></div></div>
        <label>{{ tx.sourceTask }}<input v-model="sourceTaskId" placeholder="task-..." /></label>
        <label>{{ tx.dataSource }}<select v-model="dataSource"><option value="mock">{{ tx.archiveSource }}</option><option value="real">{{ tx.enterpriseSource }}</option></select></label>
        <button class="primary wide" :disabled="busy || !sourceTaskId" @click="replay">{{ tx.runReplay }}</button>
        <div v-if="report" class="report">
          <div class="report-head"><span>{{ report.replay_id }}</span><b :class="report.status">{{ reportStatus(report.status) }}</b></div>
          <div class="metrics">
            <div><span>{{ tx.onTime }}</span><strong>{{ pct(report.replay_metrics.on_time_rate) }}</strong><small>{{ signed(report.deltas.on_time_rate, true) }}</small></div>
            <div><span>{{ tx.load }}</span><strong>{{ pct(report.replay_metrics.average_utilization) }}</strong><small>{{ signed(report.deltas.average_utilization, true) }}</small></div>
            <div><span>{{ tx.overtime }}</span><strong>{{ report.replay_metrics.overtime_minutes }}</strong><small>{{ signed(report.deltas.overtime_minutes) }}</small></div>
            <div><span>{{ tx.changeover }}</span><strong>{{ report.replay_metrics.changeover_count }}</strong><small>{{ signed(report.deltas.changeover_count) }}</small></div>
          </div>
          <p>{{ tx.publishBlocked }}</p>
        </div>
      </article>
    </div>
    <article class="ops-card history-card">
      <div class="card-title"><div><h3>{{ tx.history }}</h3><p>{{ tx.historyHint }}</p></div></div>
      <div v-if="history.length" class="history-list"><div v-for="item in history" :key="item.version"><b>V{{ item.version }}</b><span :class="['mode',item.mode]">{{ modeLabel(item.mode) }}</span><span>{{ item.traffic_percent }}%</span><span>{{ item.updated_by }}</span><span>{{ item.reason || '—' }}</span><time>{{ new Date(item.updated_at).toLocaleString() }}</time></div></div>
      <p v-else class="empty">{{ tx.empty }}</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getRolloutHistory, getRolloutPolicy, rollbackRolloutPolicy, runHistoricalReplay, updateRolloutPolicy } from '../services/api'
import type { HistoricalReplayReport, RolloutPolicy } from '../types'
type Locale='zh-TW'|'zh-CN'|'en-US'
const props=defineProps<{locale:Locale}>()
const words={
  'zh-TW':{title:'發佈控制中心',subtitle:'按車間管理放量策略，使用歷史工單驗證計畫品質。',rollout:'單車間灰度策略',rolloutHint:'控制核准計畫是否進入 MES。',workshop:'車間代碼',traffic:'放量比例',reason:'變更原因',reasonHint:'輸入變更單或操作原因',rollback:'回退上一版',save:'儲存策略',replay:'歷史資料回放',replayHint:'重新求解並與同期人工计划指標比較。',sourceTask:'來源任務',dataSource:'資料來源',archiveSource:'規劃資料庫',enterpriseSource:'企業整合資料源',runReplay:'執行回放',onTime:'準時率',load:'平均負載',overtime:'加班分鐘',changeover:'換線次數',publishBlocked:'回放結果僅用於驗證，不會下發 MES。',history:'策略版本',historyHint:'每次修改與回退都生成新的審計版本。',empty:'尚無策略變更記錄',saved:'策略已更新',rolled:'已恢復上一版策略',done:'歷史回放已完成',failed:'操作失敗'},
  'zh-CN':{title:'发布控制中心',subtitle:'按车间管理放量策略，使用历史工单验证计划质量。',rollout:'单车间灰度策略',rolloutHint:'控制批准计划是否进入 MES。',workshop:'车间编码',traffic:'放量比例',reason:'变更原因',reasonHint:'输入变更单或操作原因',rollback:'回退上一版',save:'保存策略',replay:'历史数据回放',replayHint:'重新求解并与同期人工计划指标对比。',sourceTask:'来源任务',dataSource:'数据来源',archiveSource:'规划数据库',enterpriseSource:'企业集成数据源',runReplay:'执行回放',onTime:'准时率',load:'平均负载',overtime:'加班分钟',changeover:'换线次数',publishBlocked:'回放结果只用于验证，不会下发 MES。',history:'策略版本',historyHint:'每次修改与回退都会生成新的审计版本。',empty:'暂无策略变更记录',saved:'策略已更新',rolled:'已恢复上一版策略',done:'历史回放已完成',failed:'操作失败'},
  'en-US':{title:'Release Control',subtitle:'Control release by workshop and validate plan quality against historical orders.',rollout:'Workshop rollout policy',rolloutHint:'Controls whether approved plans are released to MES.',workshop:'Workshop',traffic:'Release traffic',reason:'Change reason',reasonHint:'Change ticket or operational reason',rollback:'Restore previous',save:'Save policy',replay:'Historical replay',replayHint:'Re-solve orders and compare against the manual plan baseline.',sourceTask:'Source task',dataSource:'Data source',archiveSource:'Planning database',enterpriseSource:'Enterprise integration',runReplay:'Run replay',onTime:'On-time rate',load:'Average load',overtime:'Overtime min',changeover:'Changeovers',publishBlocked:'Replay results are validation-only and are never published to MES.',history:'Policy versions',historyHint:'Every update and rollback creates a new audit version.',empty:'No policy changes recorded',saved:'Policy updated',rolled:'Previous policy restored',done:'Historical replay completed',failed:'Operation failed'},
}
const tx=computed(()=>words[props.locale])
const modes=computed(()=>[
  {value:'shadow' as const,label:props.locale==='zh-TW'?'影子驗證':props.locale==='zh-CN'?'影子验证':'Shadow',hint:props.locale==='zh-TW'?'只記錄不下發':props.locale==='zh-CN'?'只记录不下发':'Record only'},
  {value:'canary' as const,label:props.locale==='zh-TW'?'小流量灰度':props.locale==='zh-CN'?'小流量灰度':'Canary',hint:props.locale==='zh-TW'?'按比例放量':props.locale==='zh-CN'?'按比例放量':'Percentage rollout'},
  {value:'active' as const,label:props.locale==='zh-TW'?'正式運行':props.locale==='zh-CN'?'正式运行':'Active',hint:props.locale==='zh-TW'?'正式下發':props.locale==='zh-CN'?'正式下发':'Full release'},
])
const workshopId=ref('DIP-A'), policy=ref<RolloutPolicy>(), history=ref<RolloutPolicy[]>([]), mode=ref<'shadow'|'canary'|'active'>('shadow'), traffic=ref(10), reason=ref(''), busy=ref(false), notice=ref(''), sourceTaskId=ref(''), dataSource=ref<'mock'|'real'>('mock'), report=ref<HistoricalReplayReport>()
async function loadPolicy(){busy.value=true;try{policy.value=await getRolloutPolicy(workshopId.value);mode.value=policy.value.mode==='disabled'?'shadow':policy.value.mode;traffic.value=policy.value.traffic_percent||10;history.value=await getRolloutHistory(workshopId.value)}catch(e){notice.value=`${tx.value.failed}: ${(e as Error).message}`}finally{busy.value=false}}
async function save(){busy.value=true;try{policy.value=await updateRolloutPolicy(workshopId.value,{mode:mode.value,traffic_percent:traffic.value,updated_by:'release-operator',reason:reason.value,expected_version:policy.value?.version||0});notice.value=tx.value.saved;await loadPolicy()}catch(e){notice.value=`${tx.value.failed}: ${(e as Error).message}`}finally{busy.value=false}}
async function rollback(){if(!policy.value)return;busy.value=true;try{policy.value=await rollbackRolloutPolicy(workshopId.value,policy.value.version);notice.value=tx.value.rolled;await loadPolicy()}catch(e){notice.value=`${tx.value.failed}: ${(e as Error).message}`}finally{busy.value=false}}
async function replay(){busy.value=true;try{report.value=await runHistoricalReplay(sourceTaskId.value,dataSource.value);notice.value=tx.value.done}catch(e){notice.value=`${tx.value.failed}: ${(e as Error).message}`}finally{busy.value=false}}
const pct=(v:number)=>`${Math.round(v*100)}%`;const signed=(v:number,percent=false)=>`${v>=0?'+':''}${percent?(v*100).toFixed(1)+'%':v.toFixed(0)}`
function modeLabel(value:string){if(value==='disabled')return props.locale==='zh-TW'?'停止發佈':props.locale==='zh-CN'?'停止发布':'Disabled';const found=modes.value.find(item=>item.value===value);return found?.label||value}
function reportStatus(value:string){if(props.locale==='en-US')return value==='passed'?'Passed':'Needs review';return value==='passed'?(props.locale==='zh-TW'?'驗證通過':'验证通过'):(props.locale==='zh-TW'?'需要覆核':'需要复核')}
onMounted(loadPolicy)
</script>

<style scoped>
.ops-page{display:grid;gap:18px}.ops-head{display:flex;justify-content:space-between;align-items:end}.ops-head h2{margin:0;font-size:24px}.ops-head p,.card-title p{margin:6px 0 0;color:#6d7785}.scope{padding:7px 12px;border:1px solid #ccd4dc;border-radius:4px;font:12px monospace}.ops-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.ops-card{background:#fff;border:1px solid #dbe1e7;border-radius:6px;padding:22px;box-shadow:0 8px 24px rgba(30,45,60,.05)}.card-title{display:flex;justify-content:space-between;margin-bottom:18px}.card-title h3{margin:0;font-size:17px}.card-title>b{font:13px monospace;color:#2475c7}.ops-card label{display:grid;grid-template-columns:110px 1fr auto;align-items:center;gap:10px;margin:12px 0;font-size:13px;color:#4b5663}.ops-card input,.ops-card select{border:1px solid #cfd7df;border-radius:4px;padding:9px 10px;background:#fff}.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:18px 0}.mode-grid button{display:grid;text-align:left;padding:12px;border:1px solid #d7dee5;background:#f8fafb;border-radius:4px}.mode-grid button.active{border-color:#2475c7;background:#edf6ff}.mode-grid small{margin-top:5px;color:#76808b}.actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}.primary,.secondary{border:0;border-radius:4px;padding:10px 16px}.primary{background:#1769aa;color:#fff}.secondary{background:#e9edf1;color:#344250}.wide{width:100%;margin:10px 0}.notice{padding:9px;background:#f2f7fb;color:#315b78}.report{margin-top:18px;border-top:1px solid #e0e5ea;padding-top:15px}.report-head{display:flex;justify-content:space-between;font:12px monospace}.report-head b.passed{color:#17804b}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.metrics div{display:grid;padding:10px;background:#f7f9fb}.metrics span,.metrics small{font-size:11px;color:#6d7785}.metrics strong{font-size:20px;margin:3px 0}.history-list>div{display:grid;grid-template-columns:50px 110px 60px 120px 1fr 170px;gap:12px;padding:11px;border-bottom:1px solid #edf0f3;font-size:13px}.mode{font-size:11px}.empty{color:#7c8792}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #1769aa;outline-offset:2px}@media(max-width:1000px){.ops-grid{grid-template-columns:1fr}.history-list>div{grid-template-columns:45px 100px 50px 1fr}.history-list time,.history-list span:nth-child(5){display:none}}
</style>
