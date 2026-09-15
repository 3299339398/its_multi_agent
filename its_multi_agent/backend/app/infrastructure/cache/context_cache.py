import json
from typing import Any, Dict, List, Optional

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.logging.logger import logger

try:
    import redis
except ImportError:
    redis = None


class ContextCache:
    """Redis 上下文缓存。缓存不可用时静默回退到持久化归档。"""

    def __init__(self) -> None:
        self._client = None
        if redis is not None and settings.REDIS_URL:
            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )

    def get(self, user_id: str, session_id: str) -> Optional[List[Dict[str, Any]]]:
        if self._client is None:
            return None
        try:
            value = self._client.get(self._key(user_id, session_id))
            return json.loads(value) if value else None
        except Exception as error:
            logger.debug("Redis 上下文读取失败，回退 SQLite: %s", error)
            return None

    def set(self, user_id: str, session_id: str, context: List[Dict[str, Any]]) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(
                self._key(user_id, session_id),
                settings.REDIS_CONTEXT_TTL,
                json.dumps(context, ensure_ascii=False),
            )
        except Exception as error:
            logger.debug("Redis 上下文写入失败，继续使用 SQLite: %s", error)

    def invalidate(self, user_id: str, session_id: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(self._key(user_id, session_id))
        except Exception as error:
            logger.debug("Redis 上下文失效操作失败: %s", error)

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"context:{user_id}:{session_id}"


context_cache = ContextCache()
