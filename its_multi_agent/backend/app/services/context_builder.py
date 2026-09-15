from typing import Any, Dict, List

from its_multi_agent.backend.app.infrastructure.cache.context_cache import context_cache
from its_multi_agent.backend.app.repositories.sqlite_session_repository import session_repository
from its_multi_agent.backend.app.services.conversation_memory import SUMMARY_PREFIX, task_memory_from_history


class ContextBuilder:
    """将归档消息、摘要和实时缓存组装成 Agent 输入。"""

    SUMMARY_PREFIX = SUMMARY_PREFIX
    MEMORY_PREFIX = "以下是与当前问题相关的长期用户记忆，仅在确实相关时使用：\n"

    def __init__(self, repository=session_repository, cache=context_cache):
        self._repository = repository
        self._cache = cache

    def build(
        self, user_id: str, session_id: str, history: List[Dict[str, Any]], max_turn: int = 20,
        force_refresh: bool = False, memory_context: str = "",
    ) -> List[Dict[str, Any]]:
        if not force_refresh:
            cached = self._cache.get(user_id, session_id)
            if cached:
                return cached

        system_messages = self._base_system_messages(history)
        visible_messages = [message for message in history if message.get("role") != "system"]
        recent_messages = visible_messages[-max(2, max_turn * 2):]
        summary = self._repository.get_summary(user_id, session_id)

        context = list(system_messages)
        if summary:
            context.append({
                "role": "system",
                "content": self.SUMMARY_PREFIX + summary,
            })
        if memory_context:
            context.append({
                "role": "system",
                "content": self.MEMORY_PREFIX + memory_context,
            })
        task_memory = task_memory_from_history(visible_messages)
        if task_memory:
            context.append({"role": "system", "content": "当前任务记忆（结构化，仅供核对）：\n" + task_memory})
        context.extend(recent_messages)
        self._cache.set(user_id, session_id, context)
        return context

    def append_user_message(
        self, user_id: str, session_id: str, content: str, max_turn: int = 20,
        memory_context: str = "", attachments: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]] | None:
        """在已有缓存上下文上追加用户消息；没有缓存时返回 None 触发归档回源。"""
        cached = self._cache.get(user_id, session_id)
        if not cached:
            return None

        system_messages = self._base_system_messages(cached)
        visible_messages = [message for message in cached if message.get("role") != "system"]
        message = {"role": "user", "content": content}
        if attachments:
            message["attachments"] = attachments
        visible_messages.append(message)
        limit = max(2, max_turn * 2)
        summary = self._repository.get_summary(user_id, session_id)
        context = list(system_messages)
        if summary:
            context.append({
                "role": "system",
                "content": self.SUMMARY_PREFIX + summary,
            })
        if memory_context:
            context.append({
                "role": "system",
                "content": self.MEMORY_PREFIX + memory_context,
            })
        task_memory = task_memory_from_history(visible_messages)
        if task_memory:
            context.append({"role": "system", "content": "当前任务记忆（结构化，仅供核对）：\n" + task_memory})
        context.extend(visible_messages[-limit:])
        self._cache.set(user_id, session_id, context)
        return context

    def _base_system_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            message
            for message in messages
            if message.get("role") == "system"
            and not str(message.get("content", "")).startswith(
                (self.SUMMARY_PREFIX, self.MEMORY_PREFIX)
            )
        ]


context_builder = ContextBuilder()
