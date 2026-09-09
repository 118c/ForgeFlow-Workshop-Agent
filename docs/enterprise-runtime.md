# 企业运行配置

ForgeFlow 提供两种明确隔离的运行剖面。

| 剖面 | 持久化 | 协调 | 任务执行 | 用途 |
|---|---|---|---|---|
| `local` | SQLite | 进程内锁与幂等缓存 | inline | 本机开发、面试展示 |
| `enterprise` | PostgreSQL | Redis 分布式锁与幂等缓存 | Celery | 多实例部署与业务联调 |

## 启动企业基础设施

```bash
docker compose up --build
```

API 为 `http://localhost:8000`。Celery worker 执行排程任务，Celery beat 周期扫描 Transactional Outbox；审核事实与 MES 下发意图在同一个 PostgreSQL 事务提交，外部调用失败会按退避策略重试。

真实环境必须通过部署平台注入 `POSTGRES_PASSWORD`、`BUSINESS_API_BASE_URL` 与 `BUSINESS_API_KEY`，并替换示例凭据。数据库表当前由应用引导创建；正式变更流程应接入 Alembic 并由发布流水线单独执行迁移。

## 队列接口

- `POST /api/scheduling/jobs`：以 `Idempotency-Key` 请求头提交任务；
- `GET /api/scheduling/jobs/{job_id}`：读取 queued/running/succeeded/failed 状态；
- 原同步与 SSE 接口继续保留，保证旧前端不需要改造。

## 影子运行

先生成候选任务，再调用 `POST /api/scheduling/shadow-runs`。真实模式会并行读取 MES、WMS、EAM、HR、QMS 的版本化快照，执行七类一致性检查并输出与人工计划的指标差异。影子报告固定 `publish_blocked=true`，不会触发 MES 下发。

详细上游字段定义见 [OpenAPI 数据契约](integration-contracts.openapi.yaml)。
