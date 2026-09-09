# ForgeFlow — 车间多任务作业规划 Agent

ForgeFlow 是一个面向排程主管、线长和 IE 工程师的制造作业规划参考实现。系统以 FastAPI、LangGraph 和 Vue 3 为基础，将资源读取、班组校验、工位分配、方案生成和人工审核组织成可恢复、可追踪的五节点流程。

项目提供可直接运行的内置数据适配器，同时保留 MES、设备平台和排班系统的 HTTP 接口边界。当前版本适合作为业务验证、系统联调和生产化改造的工程基线；它不是任何企业的生产源码，也不代表已经通过真实产线验收。

## 功能

- 计划编排：通过 SSE 实时展示五节点执行状态、耗时和降级信息；
- 任务中心：查询任务、状态、车间、计划版本及执行节点；
- 审核中心：支持核准、修改、退回和乐观锁版本校验；
- 资源台账：展示设备状态、OEE、产能、维护窗口、班组到岗和技能矩阵；
- 版本比较：比较准时率、平均负载、加班、换线和风险；
- 运行追踪：按 `task_id` 与 `trace_id` 查看节点摘要和人工操作记录；
- 多模型适配：DeepSeek、阿里云百炼和 OpenAI 兼容接口，可按配置降级；
- 三语界面：默认繁体中文，支持简体中文与英文。

## 架构

```text
Vue 3 工作台
      │ HTTP + SSE
      ▼
FastAPI API ─────────────── request_id / 参数校验
      │
      ▼
SchedulingService ──────── SQLite TaskRepository
      │                    任务快照 / 版本历史 / 审核记录
      ▼
LangGraph StateGraph
  设备资源 → 班组与工单 → 工位分配 → 方案生成 → 人工审核
      │
      ├── Built-in WorkshopGateway
      └── HTTP WorkshopGateway ── MES / EAM / HR

确定性规划器负责生成可执行基线
LLM 负责方案说明、风险摘要和建议增强
人工审核负责不可逆的计划下发决策
```

LLM 不直接决定生产下发。业务约束和分配规则在确定性规划层完成，人工核准后才调用 MES 发布边界。外部接口或模型不可用时，节点记录降级原因并继续生成结构化基线方案。

## 本地运行

环境要求：Python 3.11+、Node.js 22+。

```powershell
git clone <your-repository-url>
cd map-traveller

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

Copy-Item backend/.env.example backend/.env

cd backend
python run.py
```

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问：

- 工作台：`http://localhost:5173`
- OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

默认配置使用内置基线数据和确定性规划器，不需要配置 LLM 密钥，也不会访问外部业务系统。

## 配置真实接口

复制 `backend/.env.example` 后配置：

```dotenv
BUSINESS_API_BASE_URL=https://gateway.example.internal
BUSINESS_API_KEY=
BUSINESS_API_TIMEOUT_SECONDS=5
```

现有业务网关契约：

| 系统 | 方法与路径 | 数据范围 |
|---|---|---|
| EAM / 设备平台 | `GET /v1/equipment/available` | 设备、工位、能力、状态、OEE、产能 |
| HR / 排班 | `GET /v1/workforce/shifts` | 班次、班组、到岗、技能 |
| MES | `GET /v1/mes/work-orders` | 待排工单与工艺路线 |
| MES | `POST /v1/mes/schedule-plans` | 审核后的计划下发 |

企业字段映射集中在 `backend/app/services/business_gateway.py`，Agent 节点不直接依赖外部系统的数据结构。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/scheduling/plan/stream` | SSE 流式执行作业规划 |
| POST | `/api/scheduling/plan` | 同步创建规划任务 |
| GET | `/api/scheduling/tasks` | 查询最近任务 |
| GET | `/api/scheduling/tasks/{task_id}` | 恢复任务快照 |
| POST | `/api/scheduling/tasks/{task_id}/review` | 核准、修改或退回计划 |
| GET | `/api/scheduling/resources` | 获取可追溯资源快照 |
| GET | `/api/scheduling/plans/versions` | 获取方案版本与比较指标 |
| GET | `/api/config/runtime` | 查询运行配置与模型状态 |

旧 SSE 地址 `/api/trip/plan/stream` 仅作为迁移兼容层保留。

## 测试

```powershell
cd backend
pip install -r requirements-dev.txt
pytest -q

cd ../frontend
npm ci
npm run typecheck
npm run build
```

浏览器端到端测试需要安装 Chromium：

```powershell
python -m playwright install chromium
python tests/ui_smoke.py
```

GitHub Actions 会在每次 push 和 pull request 时执行后端测试、前端类型检查与生产构建。

## 当前边界

当前实现仍属于工程化基线，生产接入前需要完成：

- 使用 PostgreSQL、Redis 和任务队列替换单机状态组件；
- 引入 Transactional Outbox，保证审核事实与 MES 下发的一致性；
- 接入 OR-Tools CP-SAT，补齐物料、治具、换线、设备日历和人员技能硬约束；
- 完成 SSO/RBAC、密钥托管、不可篡改审计、监控告警和多实例容灾；
- 使用真实历史数据进行影子运行、人工计划对照和单车间灰度验证。

完整演进路径与验收门槛见[生产化落地方案](docs/生產化落地方案.md)。

## 安全说明

- 不要提交 `backend/.env`、数据库文件或真实业务数据；
- 不要在浏览器环境变量中保存服务端密钥；
- 示例工厂、工单、设备和班组编号均为非生产基线数据；
- 真实环境应通过 Vault/KMS 管理密钥，并在 API Gateway 层启用身份认证和访问控制。
