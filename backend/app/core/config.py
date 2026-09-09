"""集中配置。生产密钥只从环境变量读取。"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ForgeFlow 车间多任务作业规划 Agent"
    app_version: str = "3.0.0"
    environment: str = "demo"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    llm_provider: str = "deepseek"
    llm_fallback_order: str = "deepseek,aliyun,openai"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    aliyun_dashscope_api_key: str = ""
    aliyun_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    aliyun_model: str = "qwen-plus"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    business_api_base_url: str = ""
    business_api_key: str = ""
    business_api_timeout_seconds: float = 5.0
    task_db_path: str = "./data/forgeflow.db"
    mock_latency_ms: int = 180

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "forgeflow-workshop-agent"
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }

    def get_cors_origins_list(self) -> List[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def get_llm_fallback_order(self) -> List[str]:
        return [item.strip() for item in self.llm_fallback_order.split(",") if item.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
