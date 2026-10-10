from typing import Any, Dict, List

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.repositories.sqlite_session_repository import session_repository
from its_multi_agent.backend.app.services.context_builder import context_builder
from its_multi_agent.backend.app.infrastructure.cache.context_cache import context_cache


class SessionService:
    """会话归档与推理上下文服务。"""

    DEFAULT_SESSION_ID = "default_session"
    # 仅保留当前需要的消息；更早的内容仍保存在 SQLite 归档和摘要中。
    DEFAULT_CONTEXT_MESSAGES = 40

    def __init__(self):
        self._repo = session_repository
        self._cache = context_cache

    def prepare_history(
        self, user_id: str, session_id: str, user_input: str, max_turn: int = 20,
        memory_context: str = "", attachments: List[Dict[str, Any]] | None = None,
        workspace_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """归档完整消息，只向 Agent 暴露摘要和最近消息。"""
        target_session_id = self._scoped_session_id(session_id, workspace_id)
        user_message = {"role": "user", "content": user_input}
        if attachments:
            user_message["attachments"] = attachments
        self._repo.append_message(user_id, target_session_id, user_message)
        cached_context = context_builder.append_user_message(
            user_id, target_session_id, user_input, max_turn, memory_context, attachments=attachments,
        )
        if cached_context is not None:
            return cached_context
        full_history = [self._system_message(target_session_id)] + (
            self._repo.load_recent_session(user_id, target_session_id, max(40, max_turn * 2)) or []
        )
        return context_builder.build(
            user_id, target_session_id, full_history, max_turn,
            force_refresh=True, memory_context=memory_context,
        )

    def load_history(self, user_id: str, session_id: str, workspace_id: str = "default") -> List[Dict[str, Any]]:
        target_session_id = self._scoped_session_id(session_id, workspace_id)
        history = self._repo.load_session(user_id, target_session_id)
        if history is None:
            return [self._system_message(target_session_id)]
        return history

    def save_history(self, user_id: str, session_id: str, chat_history: List[Dict[str, Any]], workspace_id: str = "default") -> None:
        if not chat_history:
            return
        target_session_id = self._scoped_session_id(session_id, workspace_id)
        assistant_messages = [item for item in chat_history if item.get("role") == "assistant"]
        if assistant_messages:
            self._repo.append_message(user_id, target_session_id, assistant_messages[-1])
            history = [self._system_message(target_session_id)] + (
                self._repo.load_recent_session(user_id, target_session_id, 40) or []
            )
            context_builder.build(user_id, target_session_id, history, force_refresh=True)

    def get_all_sessions_memory(self, user_id: str) -> List[Dict[str, Any]]:
        formatted_sessions = []
        for session_id, create_time, data_or_error in self._repo.get_all_sessions_metadata(user_id):
            item = {"session_id": session_id, "create_time": create_time}
            if isinstance(data_or_error, Exception):
                logger.error("读取会话 %s 失败: %s", session_id, data_or_error)
                item.update({"memory": [], "total_messages": 0, "error": "无法读取会话数据"})
            else:
                visible = [message for message in data_or_error if message.get("role") != "system"]
                item.update({"memory": visible, "total_messages": len(visible)})
            formatted_sessions.append(item)
        return formatted_sessions

    def list_sessions(self, user_id: str, page: int = 1, page_size: int = 30, workspace_id: str = "default") -> dict:
        result = self._repo.list_sessions(user_id, page, page_size, session_prefix=self._prefix(workspace_id))
        prefix = self._prefix(workspace_id)
        if prefix:
            for item in result["sessions"]:
                item["session_id"] = item["session_id"][len(prefix):]
        return result

    def load_message_page(self, user_id: str, session_id: str, page_size: int = 20,
                          before_id: int | None = None, workspace_id: str = "default") -> dict | None:
        return self._repo.load_message_page(user_id, self._scoped_session_id(session_id, workspace_id), page_size, before_id)

    def delete_session(self, user_id: str, session_id: str, workspace_id: str = "default") -> bool:
        target = self._scoped_session_id(session_id, workspace_id)
        deleted = self._repo.delete_session(user_id, target)
        if deleted:
            self._cache.invalidate(user_id, target)
        return deleted

    @staticmethod
    def _prefix(workspace_id: str) -> str:
        return "" if not workspace_id or workspace_id == "default" else f"ws_{workspace_id}__"

    def _scoped_session_id(self, session_id: str, workspace_id: str) -> str:
        return self._prefix(workspace_id) + (session_id or self.DEFAULT_SESSION_ID)

    @staticmethod
    def _system_message(session_id: str) -> Dict[str, str]:
        return {
            "role": "system",
            "content": f"你是一个有记忆的智能体助手，请基于上下文历史会话用户问题 (会话ID {session_id})",
        }


session_service = SessionService()
