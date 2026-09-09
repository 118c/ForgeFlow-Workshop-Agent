<template>
  <section class="workspace-view">
    <div class="workbench-head">
      <div><h2>{{ tx.title }}</h2><p>{{ tx.subtitle }}</p></div>
      <div class="filters"><input v-model="factoryId" :aria-label="tx.factory" /><input v-model="workshopId" :aria-label="tx.workshop" /><input v-model="productionDate" type="date" :aria-label="tx.date" /><button :disabled="loading" @click="load">↻ {{ tx.refresh }}</button></div>
    </div>

    <template v-if="snapshot">
      <div class="source-ribbon panel"><div><span>{{ tx.sourceVersion }}</span><b class="mono">{{ snapshot.source_version }}</b></div><div><span>{{ tx.captureTime }}</span><b>{{ formatDateTime(locale,snapshot.captured_at) }}</b></div><div><span>{{ tx.scope }}</span><b>{{ snapshot.factory_id }} / {{ snapshot.workshop_id }}</b></div><div class="quality"><i></i><span>{{ tx.quality }}</span><b>{{ tx.complete }}</b></div></div>

      <div class="resource-kpis">
        <article><span>{{ tx.availability }}</span><b>{{ availableRate }}<small>%</small></b><em>{{ availableCount }}/{{ snapshot.devices.length }} {{ tx.units }}</em></article>
        <article><span>{{ tx.oee }}</span><b>{{ averageOee }}<small>%</small></b><em>{{ tx.weighted }}</em></article>
        <article><span>{{ tx.headcount }}</span><b>{{ totalHeadcount }}</b><em>{{ snapshot.shifts.length }} {{ tx.shifts }}</em></article>
        <article><span>{{ tx.attendance }}</span><b>{{ attendance }}<small>%</small></b><em>{{ tx.rosterVerified }}</em></article>
      </div>

      <div class="resource-layout">
        <article class="panel equipment-panel">
          <div class="section-head"><div><h3>{{ tx.equipment }}</h3><p>{{ tx.equipmentHint }}</p></div><span>{{ maintenanceCount }} {{ tx.maintenance }}</span></div>
          <div class="line-map" v-for="line in lines" :key="line.code">
            <div class="line-name"><b>{{ line.code }}</b><small>{{ line.devices.length }} {{ tx.units }}</small></div>
            <div class="line-track"><div v-for="device in line.devices" :key="device.device_id" :class="['machine',device.status]" :title="device.name"><i></i><span>{{ device.device_id }}</span><small>{{ Math.round(device.oee*100) }}%</small></div></div>
          </div>
          <div class="equipment-table">
            <div class="equipment-row table-head"><span>{{ tx.device }}</span><span>{{ tx.station }}</span><span>{{ tx.capability }}</span><span>{{ tx.capacity }}</span><span>{{ tx.oee }}</span><span>{{ tx.state }}</span></div>
            <div class="equipment-row" v-for="device in snapshot.devices" :key="device.device_id"><span><b>{{ device.name }}</b><small class="mono">{{ device.device_id }} · {{ device.line_code }}</small></span><span class="mono">{{ device.station_code }}</span><span><i class="cap" v-for="item in device.capability" :key="item">{{ processName(item) }}</i></span><span>{{ formatNumber(locale,device.capacity_per_hour) }} <small>{{ tx.perHour }}</small></span><span><b :class="oeeClass(device.oee)">{{ Math.round(device.oee*100) }}%</b></span><span><i :class="['state-dot',device.status]"></i>{{ stateName(device.status) }}</span></div>
          </div>
        </article>

        <aside class="panel workforce-panel">
          <div class="section-head"><div><h3>{{ tx.workforce }}</h3><p>{{ tx.workforceHint }}</p></div></div>
          <div class="shift-card" v-for="shift in snapshot.shifts" :key="shift.shift_code">
            <div class="shift-head"><div><b>{{ teamName(shift.team_name) }}</b><small class="mono">{{ shift.shift_code }} · {{ clock(shift.start_at) }}–{{ clock(shift.end_at) }}</small></div><strong>{{ shift.headcount }}<small>{{ tx.people }}</small></strong></div>
            <div class="attendance-bar"><span :style="{width:`${shift.attendance_rate*100}%`}"></span></div>
            <div class="shift-meta"><span>{{ tx.attendance }}</span><b>{{ Math.round(shift.attendance_rate*100) }}%</b></div>
            <div class="skills"><span v-for="skill in shift.skill_tags" :key="skill">✓ {{ processName(skill) }}</span></div>
          </div>
          <section class="maintenance-box"><h4>{{ tx.maintenanceWindow }}</h4><div v-for="device in maintenanceDevices" :key="device.device_id"><i></i><p><b>{{ device.device_id }} · {{ device.name }}</b><small>{{ device.next_maintenance_at ? formatDateTime(locale,device.next_maintenance_at) : tx.inProgress }}</small></p></div><p v-if="!maintenanceDevices.length" class="empty-note">{{ tx.noMaintenance }}</p></section>
        </aside>
      </div>
    </template>
    <div v-else-if="!loading" class="panel empty">{{ tx.empty }}</div>
    <p v-if="error" class="error-line">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { getResources } from '../services/api'
import type { DeviceResource,ResourceSnapshot } from '../types'
import { formatDateTime,formatNumber,type Locale } from '../utils/workbench'
const props=defineProps<{locale:Locale}>()
const snapshot=ref<ResourceSnapshot|null>(null),loading=ref(false),error=ref(''),factoryId=ref('FOX-SZ-01'),workshopId=ref('DIP-A'),productionDate=ref('2026-09-10')
const copy={
  'zh-TW':{title:'資源台帳',subtitle:'確認設備能力、維護窗口、班組到崗與技能覆蓋後再進入排程。',factory:'工廠代碼',workshop:'車間代碼',date:'生產日期',refresh:'更新資源',sourceVersion:'來源版本',captureTime:'資料擷取時間',scope:'資源範圍',quality:'資料品質',complete:'關鍵欄位完整',availability:'設備可用率',units:'台設備',oee:'平均 OEE',weighted:'可用設備算術平均',headcount:'當班總人數',shifts:'個班次',attendance:'平均到崗率',rosterVerified:'排班資料已校驗',equipment:'設備能力台帳',equipmentHint:'依線體呈現可用狀態、產能與製程能力。',maintenance:'台維護中',device:'設備',station:'工位',capability:'製程能力',capacity:'額定產能',state:'目前狀態',perHour:'件/時',available:'可用',maintenanceState:'維護中',offline:'離線',workforce:'班組技能矩陣',workforceHint:'班次、人力與技能覆蓋。',people:'人',maintenanceWindow:'維護窗口',inProgress:'目前處於維護狀態',noMaintenance:'目前沒有維護窗口',empty:'尚未取得資源資料',processAssembly:'組裝',processTest:'測試',processPackage:'包裝'},
  'zh-CN':{title:'资源台账',subtitle:'确认设备能力、维护窗口、班组到岗与技能覆盖后再进入排产。',factory:'工厂编码',workshop:'车间编码',date:'生产日期',refresh:'更新资源',sourceVersion:'来源版本',captureTime:'数据采集时间',scope:'资源范围',quality:'数据质量',complete:'关键字段完整',availability:'设备可用率',units:'台设备',oee:'平均 OEE',weighted:'可用设备算术平均',headcount:'当班总人数',shifts:'个班次',attendance:'平均到岗率',rosterVerified:'排班数据已校验',equipment:'设备能力台账',equipmentHint:'按线体呈现可用状态、产能与工艺能力。',maintenance:'台维护中',device:'设备',station:'工位',capability:'工艺能力',capacity:'额定产能',state:'当前状态',perHour:'件/时',available:'可用',maintenanceState:'维护中',offline:'离线',workforce:'班组技能矩阵',workforceHint:'班次、人力与技能覆盖。',people:'人',maintenanceWindow:'维护窗口',inProgress:'当前处于维护状态',noMaintenance:'当前没有维护窗口',empty:'尚未取得资源数据',processAssembly:'组装',processTest:'测试',processPackage:'包装'},
  'en-US':{title:'Resource registry',subtitle:'Verify capability, maintenance, attendance and skill coverage before planning.',factory:'Factory code',workshop:'Workshop code',date:'Production date',refresh:'Refresh resources',sourceVersion:'Source version',captureTime:'Captured at',scope:'Resource scope',quality:'Data quality',complete:'Required fields complete',availability:'Equipment availability',units:'units',oee:'Average OEE',weighted:'Available-unit mean',headcount:'On-duty headcount',shifts:'shifts',attendance:'Average attendance',rosterVerified:'Roster verified',equipment:'Equipment capability registry',equipmentHint:'Availability, capacity and process capability by line.',maintenance:'in maintenance',device:'Equipment',station:'Station',capability:'Capability',capacity:'Rated capacity',state:'Current state',perHour:'pcs/h',available:'Available',maintenanceState:'Maintenance',offline:'Offline',workforce:'Workforce skill matrix',workforceHint:'Shift, staffing and skill coverage.',people:'people',maintenanceWindow:'Maintenance window',inProgress:'Currently under maintenance',noMaintenance:'No maintenance windows',empty:'Resource data is not available',processAssembly:'Assembly',processTest:'Test',processPackage:'Packaging'},
}
const tx=computed(()=>copy[props.locale])
const availableCount=computed(()=>snapshot.value?.devices.filter(d=>d.status==='available').length||0),maintenanceCount=computed(()=>snapshot.value?.devices.filter(d=>d.status==='maintenance').length||0)
const availableRate=computed(()=>snapshot.value?.devices.length?Math.round(availableCount.value/snapshot.value.devices.length*100):0)
const averageOee=computed(()=>{const devices=snapshot.value?.devices.filter(d=>d.status==='available')||[];return devices.length?Math.round(devices.reduce((n,d)=>n+d.oee,0)/devices.length*100):0})
const totalHeadcount=computed(()=>snapshot.value?.shifts.reduce((n,s)=>n+s.headcount,0)||0),attendance=computed(()=>snapshot.value?.shifts.length?Math.round(snapshot.value.shifts.reduce((n,s)=>n+s.attendance_rate,0)/snapshot.value.shifts.length*100):0)
const maintenanceDevices=computed(()=>snapshot.value?.devices.filter(d=>d.status==='maintenance'||d.next_maintenance_at)||[])
const lines=computed(()=>{const grouped=new Map<string,DeviceResource[]>();for(const d of snapshot.value?.devices||[])grouped.set(d.line_code,[...(grouped.get(d.line_code)||[]),d]);return [...grouped.entries()].map(([code,devices])=>({code,devices}))})
function processName(v:string){return v==='组装'?tx.value.processAssembly:v==='测试'?tx.value.processTest:v==='包装'?tx.value.processPackage:v}
function stateName(v:string){return v==='available'?tx.value.available:v==='maintenance'?tx.value.maintenanceState:tx.value.offline}
function teamName(v:string){return props.locale==='en-US'?(v==='甲班'?'Team A':v==='乙班'?'Team B':v):v}
function clock(v:string){return new Date(v).toLocaleTimeString(props.locale,{hour:'2-digit',minute:'2-digit',hour12:false})}
function oeeClass(v:number){return v>=.9?'good':v>=.8?'watch':'risk'}
async function load(){loading.value=true;error.value='';try{snapshot.value=await getResources(factoryId.value,workshopId.value,productionDate.value)}catch(e:any){error.value=e.message}finally{loading.value=false}}
onMounted(load)
</script>

<style scoped>
.workspace-view{display:grid;gap:16px}.workbench-head{display:flex;justify-content:space-between;align-items:end;gap:16px}.workbench-head h2{font:600 25px "Bahnschrift";margin:0}.workbench-head p{color:var(--muted);font-size:11px;margin:6px 0 0}.filters{display:flex;gap:7px}.filters input,.filters button{background:#111a1e;color:var(--paper);border:1px solid var(--steel);padding:9px 10px;font-size:9px}.filters input{width:110px}.source-ribbon{display:grid;grid-template-columns:1fr 1.25fr 1fr 1fr;gap:1px;background:var(--steel)}.source-ribbon>div{background:#111a1e;padding:11px 14px}.source-ribbon span,.source-ribbon b{display:block}.source-ribbon span{font-size:8px;color:var(--muted)}.source-ribbon b{font-size:9px;margin-top:4px}.source-ribbon .quality{display:grid;grid-template-columns:10px 1fr;align-items:center}.quality i{grid-row:1/3;width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 5px rgba(117,198,154,.08)}.resource-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--steel);border:1px solid var(--steel)}.resource-kpis article{background:#10191d;padding:14px 17px}.resource-kpis span,.resource-kpis b,.resource-kpis em{display:block}.resource-kpis span{font-size:9px;color:var(--muted)}.resource-kpis b{font:600 24px "Bahnschrift";margin-top:4px}.resource-kpis b small{font-size:10px;color:var(--coolant)}.resource-kpis em{font-size:8px;color:#617177;font-style:normal;margin-top:2px}.resource-layout{display:grid;grid-template-columns:minmax(700px,1.45fr) minmax(290px,.55fr);gap:16px}.equipment-panel,.workforce-panel{padding:18px;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 14px,100% 100%,0 100%)}.section-head{display:flex;justify-content:space-between;align-items:start;border-bottom:1px solid var(--steel);padding-bottom:13px;margin-bottom:14px}.section-head h3{font-size:14px;margin:0}.section-head p{font-size:9px;color:var(--muted);margin:5px 0 0}.section-head>span{color:var(--safety);font-size:9px}.line-map{display:grid;grid-template-columns:90px 1fr;gap:14px;align-items:center;margin:9px 0}.line-name b,.line-name small{display:block}.line-name b{font:10px "Cascadia Mono"}.line-name small{font-size:8px;color:var(--muted);margin-top:3px}.line-track{display:flex;gap:5px;position:relative}.line-track::before{content:"";position:absolute;left:0;right:0;top:15px;height:1px;background:var(--steel)}.machine{position:relative;z-index:1;min-width:82px;border:1px solid var(--steel);background:#0e171b;padding:6px 7px;display:grid;grid-template-columns:7px 1fr auto;gap:5px;align-items:center}.machine i,.state-dot{width:5px;height:5px;border-radius:50%;background:var(--ok)}.machine.maintenance i,.state-dot.maintenance{background:var(--safety)}.machine span{font:8px "Cascadia Mono"}.machine small{font-size:7px;color:var(--muted)}.equipment-table{margin-top:17px;border-top:1px solid var(--steel)}.equipment-row{display:grid;grid-template-columns:2fr .7fr 1fr .75fr .5fr .7fr;gap:10px;align-items:center;min-height:48px;padding:7px 8px;border-bottom:1px solid rgba(38,52,58,.65);font-size:9px}.equipment-row.table-head{min-height:30px;color:#65757a;font-size:8px}.equipment-row b,.equipment-row small{display:block}.equipment-row>span:first-child small{font-size:7px;color:#607177;margin-top:3px}.equipment-row .cap{font-style:normal;border:1px solid var(--steel);padding:3px 5px;margin-right:3px;color:#91a0a3}.equipment-row b.good{color:var(--ok)}.equipment-row b.watch{color:var(--safety)}.equipment-row b.risk{color:var(--oxide)}.state-dot{display:inline-block;margin-right:5px}.shift-card{background:#0e171b;border-left:2px solid var(--coolant);padding:12px;margin-bottom:9px}.shift-head{display:flex;justify-content:space-between}.shift-head b,.shift-head small{display:block}.shift-head b{font-size:11px}.shift-head>div small{font-size:8px;color:#607177;margin-top:4px}.shift-head>strong{font:600 20px "Bahnschrift"}.shift-head>strong small{font-size:8px;color:var(--muted);display:inline;margin-left:3px}.attendance-bar{height:3px;background:#26343a;margin-top:12px}.attendance-bar span{display:block;height:100%;background:var(--ok)}.shift-meta{display:flex;justify-content:space-between;font-size:8px;color:var(--muted);padding:5px 0 9px}.skills{display:flex;gap:5px}.skills span{font-size:8px;border:1px solid var(--steel);padding:4px 6px;color:#8ea0a4}.maintenance-box{border-top:1px solid var(--steel);margin-top:17px;padding-top:14px}.maintenance-box h4{font-size:9px;color:var(--muted);margin:0 0 10px}.maintenance-box>div{display:grid;grid-template-columns:8px 1fr;gap:7px;background:rgba(245,166,35,.05);padding:9px}.maintenance-box i{width:5px;height:5px;background:var(--safety);margin-top:4px}.maintenance-box p{margin:0}.maintenance-box b,.maintenance-box small{display:block;font-size:9px}.maintenance-box small{color:var(--muted);font-size:8px;margin-top:4px}.empty,.empty-note{padding:60px;text-align:center;color:#66767b;font-size:10px}.empty-note{padding:10px}.error-line{color:#ef896e;font-size:10px}.mono{font-family:"Cascadia Mono",Consolas,monospace}@media(max-width:1100px){.resource-layout{grid-template-columns:1fr}.filters input{width:90px}}@media(max-width:760px){.workbench-head{display:block}.filters{margin-top:12px;flex-wrap:wrap}.source-ribbon,.resource-kpis{grid-template-columns:1fr 1fr}.equipment-panel{overflow:auto}.equipment-table,.line-map{min-width:720px}}
.source-ribbon .quality{display:block;position:relative;padding-left:34px}.quality i{position:absolute;left:16px;top:50%;transform:translateY(-50%)}.quality b{margin-top:4px}
</style>
