"""Redis 协调能力：幂等键、短期缓存和跨实例锁。"""

import json
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from redis import Redis
from redis.exceptions import RedisError

from .config import get_settings


class CoordinationUnavailable(RuntimeError):
    pass


class InMemoryCoordinator:
    """本地模式实现；接口与 Redis 版本一致。"""

    def __init__(self) -> None:
        self._values: Dict[str, str] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.RLock()

    def ping(self) -> bool:
        return True

    def get_json(self, key: str) -> Optional[Any]:
        value = self._values.get(key)
        return json.loads(value) if value else None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 300, nx: bool = False) -> bool:
        del ttl_seconds
        with self._guard:
            if nx and key in self._values:
                return False
            self._values[key] = json.dumps(value, ensure_ascii=False, default=str)
            return True

    @contextmanager
    def lock(self, key: str, timeout: int = 300, blocking_timeout: int = 10) -> Iterator[None]:
        del timeout
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        acquired = lock.acquire(timeout=blocking_timeout)
        if not acquired:
            raise CoordinationUnavailable("资源锁获取超时: %s" % key)
        try:
            yield
        finally:
            lock.release()


class RedisCoordinator:
    def __init__(self, url: str, prefix: str = "forgeflow") -> None:
        self.client = Redis.from_url(url, decode_responses=True, health_check_interval=30)
        self.prefix = prefix.strip(":")

    def _key(self, key: str) -> str:
        return "%s:%s" % (self.prefix, key)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisError as exc:
            raise CoordinationUnavailable("Redis 不可用") from exc

    def get_json(self, key: str) -> Optional[Any]:
        try:
            value = self.client.get(self._key(key))
            return json.loads(value) if value else None
        except (RedisError, ValueError) as exc:
            raise CoordinationUnavailable("Redis 读取失败") from exc

    def set_json(self, key: str, value: Any, ttl_seconds: int = 300, nx: bool = False) -> bool:
        try:
            return bool(
                self.client.set(
                    self._key(key),
                    json.dumps(value, ensure_ascii=False, default=str),
                    ex=ttl_seconds,
                    nx=nx,
                )
            )
        except RedisError as exc:
            raise CoordinationUnavailable("Redis 写入失败") from exc

    @contextmanager
    def lock(self, key: str, timeout: int = 300, blocking_timeout: int = 10) -> Iterator[None]:
        lock = self.client.lock(self._key("lock:%s" % key), timeout=timeout, blocking_timeout=blocking_timeout)
        try:
            if not lock.acquire(blocking=True):
                raise CoordinationUnavailable("资源锁获取超时: %s" % key)
            yield
        except RedisError as exc:
            raise CoordinationUnavailable("Redis 锁操作失败") from exc
        finally:
            try:
                if lock.owned():
                    lock.release()
            except RedisError:
                pass


_coordinator: Optional[Any] = None


def get_coordinator() -> Any:
    global _coordinator
    if _coordinator is None:
        settings = get_settings()
        _coordinator = (
            RedisCoordinator(settings.redis_url, settings.redis_key_prefix)
            if settings.enterprise_mode
            else InMemoryCoordinator()
        )
    return _coordinator
