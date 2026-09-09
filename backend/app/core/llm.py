"""兼容 OpenAI ChatCompletions 协议的多厂商 LLM 工厂。"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from .config import Settings, get_settings


def setup_langsmith() -> None:
    settings = get_settings()
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project


class LLMFactory:
    """缓存模型实例，并在厂商故障时按配置顺序降级。"""

    _instances: Dict[Tuple[str, float, int], BaseChatModel] = {}
    _circuit_open_until: Dict[str, float] = {}

    @classmethod
    def _provider_config(cls, provider: str, settings: Settings) -> Tuple[str, str, str]:
        configs = {
            "deepseek": (
                settings.deepseek_api_key,
                settings.deepseek_base_url,
                settings.deepseek_model,
            ),
            "aliyun": (
                settings.aliyun_dashscope_api_key,
                settings.aliyun_base_url,
                settings.aliyun_model,
            ),
            "openai": (
                settings.openai_api_key,
                settings.openai_base_url,
                settings.openai_model,
            ),
        }
        if provider not in configs:
            raise ValueError("不支持的 LLM 厂商: %s" % provider)
        return configs[provider]

    @classmethod
    def get_llm(
        cls,
        provider: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> BaseChatModel:
        settings = get_settings()
        provider = provider or settings.llm_provider
        api_key, base_url, model = cls._provider_config(provider, settings)
        if not api_key or api_key.startswith("your_"):
            raise ValueError("%s API Key 未配置" % provider)
        cache_key = (provider, temperature, max_tokens)
        if cache_key not in cls._instances:
            cls._instances[cache_key] = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        return cls._instances[cache_key]

    @classmethod
    def available_providers(cls) -> List[Dict[str, Any]]:
        settings = get_settings()
        result = []
        for name in ("deepseek", "aliyun", "openai"):
            key, _, model = cls._provider_config(name, settings)
            result.append(
                {
                    "name": name,
                    "model": model,
                    "configured": bool(key and not key.startswith("your_")),
                    "circuit_open": cls._circuit_open_until.get(name, 0) > time.time(),
                }
            )
        return result

    @classmethod
    async def invoke_with_failover(cls, prompt: str, preferred: str) -> Tuple[str, str]:
        settings = get_settings()
        candidates = [preferred] + [p for p in settings.get_llm_fallback_order() if p != preferred]
        failures = []
        for provider in candidates:
            if cls._circuit_open_until.get(provider, 0) > time.time():
                continue
            try:
                response = await cls.get_llm(provider).ainvoke(prompt)
                return str(response.content), provider
            except Exception as exc:  # provider 边界必须隔离
                failures.append("%s: %s" % (provider, exc))
                cls._circuit_open_until[provider] = time.time() + 30
        raise RuntimeError("所有 LLM 厂商均不可用；" + " | ".join(failures))


def extract_json_object(text: str) -> Dict[str, Any]:
    """从 Markdown 或夹杂自然语言的响应中提取第一个完整 JSON 对象。"""
    cleaned = text.strip()
    if "```" in cleaned:
        blocks = cleaned.split("```")
        cleaned = next((b[4:] if b.startswith("json") else b for b in blocks if "{" in b), cleaned)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("LLM 响应中没有 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
        elif not in_string and char == "{":
            depth += 1
        elif not in_string and char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : index + 1])
    raise ValueError("LLM 响应中的 JSON 不完整")


setup_langsmith()
