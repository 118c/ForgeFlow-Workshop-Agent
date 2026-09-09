# ForgeFlow — 车间多任务作业规划 Agent

ForgeFlow 是面向排程主管、线长和 IE 工程师的制造作业规划服务。系统以 FastAPI、LangGraph、OR-Tools 和 Vue 3 为基础，将资源读取、约束求解、方案生成和人工审核组织成可恢复、可追踪的五节点流程。

项目提供可直接运行的内置资料适配器，并实现 MES、WMS、EAM、HR、QMS 的版本化 HTTP 数据契约。运行时支持本地 SQLite/inline 和企业 PostgreSQL/Redis/Celery 两套剖面。

## 功能

- 计划编排：通过 SSE 实时呈现五节点执行状态、耗时和降级信息；
- 任务中心：查询任务、状态、车间、计划版本及执行节点；
- 审核中心：支持核准、修改、退回和乐观锁版本校验；
- 资源台账：呈现设备状态、OEE、产能、维护窗口、班组到岗和技能矩阵；
- 版本比较：比较准时率、平均负载、加班、换线和风险；
- 运行追踪：按 `task_id` 与 `trace_id` 查看节点摘要和人工操作记录；
- 可靠任务：幂等提交、Redis 分布式锁、Celery worker 与任务状态查询；
- 一致性发布：审核记录与 MES 下发意图通过 Transactional Outbox 原子提交；
- 影子验证：使用五套系统的只读快照核验七类约束，并与人工计划指标对照；
- 约束求解：使用 OR-Tools CP-SAT 处理物料、治具、换线、设备日历、人员技能和制程顺序；
- 历史回放：按历史生产日重新求解，并与同期人工计划比较准时率、负载、加班和换线；
- 灰度控制：按车间配置 shadow/canary/active 发布门禁，保留策略版本并支持一键回退；
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
SchedulingService ──────── SQLAlchemy TaskRepository
      │                    SQLite（本地）/ PostgreSQL（企业）
      ├── Redis ────────── 幂等键 / 分布式排程锁
      ├── Celery ───────── 异步任务 / 重试 / Outbox 发布
      ▼
LangGraph StateGraph
  设备资源 → 班组与工单 → 工位分配 → 方案生成 → 人工审核
      │
      ├── Built-in WorkshopGateway
      └── HTTP WorkshopGateway ── MES / WMS / EAM / HR / QMS

OR-Tools CP-SAT 负责生成满足硬约束的可执行方案
LLM 负责方案说明、风险摘要和建议增强
人工审核负责不可逆的计划下发决策
```

LLM 不直接决定生产下发。业务约束和分配规则在确定性规划层完成，人工核准后才调用 MES 发布边界。外部接口或模型不可用时，节点记录降级原因并继续生成结构化基线方案。

## 本地运行

环境要求：Python 3.11+、Node.js 22+。

```powershell
git clone <your-repository-url>
cd ForgeFlow-Workshop-Agent

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

默认配置使用内置基线资料和 CP-SAT 求解器，不需要配置 LLM 密钥，也不会访问外部业务系统。

如需启动 PostgreSQL、Redis、API、Celery worker 与 beat 的完整基础设施：

```powershell
docker compose up --build
```

两套运行剖面及部署说明见[企业运行配置](docs/enterprise-runtime.md)。

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
| EAM | `GET /v1/eam/equipment` | 设备、工位、能力、状态、OEE、产能 |
| EAM | `GET /v1/eam/tooling` | 治具兼容性、占用和维护状态 |
| HR | `GET /v1/hr/shifts` | 班次、班组、到岗、技能 |
| MES | `GET /v1/mes/work-orders` | 待排工单与工艺路线 |
| MES | `GET /v1/mes/manual-plans` | 历史人工计划对照指标 |
| WMS | `GET /v1/wms/material-readiness` | 工单齐套量、批次和预计齐套时间 |
| QMS | `GET /v1/qms/quality-constraints` | 放行、冻结、首件检查要求 |
| MES | `POST /v1/mes/schedule-plans` | 审核后的计划下发 |

所有读取接口必须返回 `source_version`、`captured_at` 和 `data`。完整字段规范见 [OpenAPI 数据契约](docs/integration-contracts.openapi.yaml)，企业字段映射集中在 `backend/app/services/business_gateway.py`，Agent 节点不直接依赖外部系统的数据结构。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/scheduling/plan/stream` | SSE 流式执行作业规划 |
| POST | `/api/scheduling/plan` | 同步创建规划任务 |
| POST | `/api/scheduling/jobs` | 幂等提交队列任务 |
| GET | `/api/scheduling/jobs/{job_id}` | 查询队列执行状态 |
| GET | `/api/scheduling/tasks` | 查询最近任务 |
| GET | `/api/scheduling/tasks/{task_id}` | 恢复任务快照 |
| POST | `/api/scheduling/tasks/{task_id}/review` | 核准、修改或退回计划 |
| GET | `/api/scheduling/resources` | 获取可追溯资源快照 |
| GET | `/api/scheduling/plans/versions` | 获取方案版本与比较指标 |
| POST | `/api/scheduling/shadow-runs` | 五系统只读影子验证 |
| GET | `/api/scheduling/shadow-runs/{shadow_run_id}` | 获取影子验证报告 |
| POST | `/api/scheduling/replays` | 执行历史生产资料回放 |
| GET | `/api/scheduling/replays/{replay_id}` | 获取人工计划对照结果 |
| GET/PUT | `/api/scheduling/rollouts/{workshop_id}` | 查询或设置单车间灰度策略 |
| GET | `/api/scheduling/rollouts/{workshop_id}/history` | 查询灰度策略版本 |
| POST | `/api/scheduling/rollouts/{workshop_id}/rollback` | 一键回退上一版策略 |
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

当前实现已经完成可替换的企业运行底座，但生产接入前仍需要完成：

- 将自动建表替换为 Alembic 受控迁移，并完成容量、故障与恢复压测；
- 完成 SSO/RBAC、密钥托管、不可篡改审计、监控告警和多实例容灾；
- 使用经授权的真实历史数据校准求解参数、回放基准和灰度准入阈值。

## 安全说明

- 不要提交 `backend/.env`、数据库文件或真实业务数据；
- 不要在浏览器环境变量中保存服务端密钥；
- 示例工厂、工单、设备和班组编号均为非生产基线数据；
- 真实环境应通过 Vault/KMS 管理密钥，并在 API Gateway 层启用身份认证和访问控制。
