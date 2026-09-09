"""ForgeFlow FastAPI 应用入口。"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ..core.config import get_settings
from ..core.llm import LLMFactory
from ..repositories.task_repository import get_task_repository
from .routes import config, scheduling


logger = logging.getLogger("forgeflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    repository = get_task_repository()
    logger.info(
        "service_started app=%s version=%s env=%s db=%s",
        settings.app_name,
        settings.app_version,
        settings.environment,
        repository.db_path,
    )
    yield
    logger.info("service_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="""
## ForgeFlow 车间多任务作业规划 Agent

五节点 LangGraph 流水线：设备资源检索 → 班组排班查询 → 工位任务分配 → 作业方案生成 → 人工审核。

- `data_source=mock`：使用内置基线数据，零外部依赖
- `data_source=real`：调用 MES / 设备 / 排班企业接口
- `demo_mode=false`：启用多厂商 LLM 与自动故障转移
        """,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or "req-%s" % uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(int((time.perf_counter() - started) * 1000))
        logger.info("request request_id=%s method=%s path=%s status=%s", request_id, request.method, request.url.path, response.status_code)
        return response

    app.include_router(scheduling.router, prefix="/api")
    app.include_router(scheduling.legacy_router, prefix="/api")
    app.include_router(config.router, prefix="/api")

    @app.get("/")
    async def root():
        return {"name": settings.app_name, "version": settings.app_version, "status": "running", "docs": "/docs"}

    @app.get("/health")
    async def health():
        providers = LLMFactory.available_providers()
        return {
            "status": "healthy",
            "environment": settings.environment,
            "database": "ready",
            "mock_gateway": "ready",
            "configured_llm_count": sum(1 for item in providers if item["configured"]),
        }

    return app


app = create_app()
