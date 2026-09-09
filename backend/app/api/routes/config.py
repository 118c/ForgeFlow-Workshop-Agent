"""可公开的运行时配置与依赖健康状态。"""

from fastapi import APIRouter

from ...core.config import get_settings
from ...core.llm import LLMFactory


router = APIRouter(prefix="/config", tags=["运行配置"])


@router.get("/runtime")
async def runtime_config():
    settings = get_settings()
    return {
        "environment": settings.environment,
        "profile": settings.app_profile,
        "task_execution": settings.task_execution_mode,
        "default_data_source": "mock" if settings.app_profile == "local" else "real",
        "business_api_configured": bool(settings.business_api_base_url),
        "providers": LLMFactory.available_providers(),
        "features": {
            "sse": True,
            "human_in_the_loop": True,
            "durable_snapshot": True,
            "provider_failover": True,
            "transactional_outbox": True,
            "shadow_validation": True,
            "cp_sat_solver": True,
            "historical_replay": True,
            "workshop_rollout": True,
        },
    }


@router.get("/llm-providers")
async def llm_providers():
    settings = get_settings()
    return {"current": settings.llm_provider, "available": LLMFactory.available_providers()}
