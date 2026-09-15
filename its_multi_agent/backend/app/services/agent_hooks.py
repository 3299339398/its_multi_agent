"""Lifecycle hooks for Agent runs.

Hooks are deliberately observational: a broken hook is logged and ignored so
that telemetry, auditing, or policy extensions cannot break a user request.
"""
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Hook = Callable[[dict[str, Any]], Any]


class AgentPolicyDenied(PermissionError):
    """Raised when a registered tool policy explicitly denies execution."""


class AgentHookManager:
    EVENTS = (
        "before_run", "before_tool_call", "tool_call", "tool_output", "agent_transition",
        "after_run", "on_error", "on_finish",
    )

    def __init__(self) -> None:
        self._hooks: dict[str, list[Hook]] = {event: [] for event in self.EVENTS}

    def register(self, event: str, hook: Hook) -> None:
        if event not in self._hooks:
            raise ValueError(f"未知 Agent Hook 事件: {event}")
        if not callable(hook):
            raise TypeError("Hook 必须是可调用对象")
        if hook not in self._hooks[event]:
            self._hooks[event].append(hook)

    def unregister(self, event: str, hook: Hook) -> bool:
        if event not in self._hooks:
            raise ValueError(f"未知 Agent Hook 事件: {event}")
        try:
            self._hooks[event].remove(hook)
            return True
        except ValueError:
            return False

    def clear(self) -> None:
        for hooks in self._hooks.values():
            hooks.clear()

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        if event not in self._hooks:
            raise ValueError(f"未知 Agent Hook 事件: {event}")
        # Snapshot allows a hook to unregister itself while handling an event.
        for hook in tuple(self._hooks[event]):
            try:
                result = hook(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Agent Hook 执行失败 event=%s hook=%s", event, getattr(hook, "__name__", type(hook).__name__))

    async def authorize_tool(self, payload: dict[str, Any]) -> None:
        """Run policy hooks; only an explicit false decision blocks a tool."""
        for hook in tuple(self._hooks["before_tool_call"]):
            try:
                result = hook(payload)
                if inspect.isawaitable(result):
                    result = await result
                denied = result is False or (isinstance(result, dict) and result.get("allow") is False)
                if denied:
                    reason = result.get("reason") if isinstance(result, dict) else "工具调用被策略拒绝"
                    raise AgentPolicyDenied(str(reason or "工具调用被策略拒绝"))
            except AgentPolicyDenied:
                raise
            except Exception:
                logger.exception("Agent 策略 Hook 执行失败 hook=%s", getattr(hook, "__name__", type(hook).__name__))

    def authorize_tool_sync(self, payload: dict[str, Any]) -> None:
        """Synchronous counterpart for blocking function tools."""
        for hook in tuple(self._hooks["before_tool_call"]):
            try:
                result = hook(payload)
                if inspect.isawaitable(result):
                    result.close()
                    raise RuntimeError("同步工具策略 Hook 不能是异步函数")
                if result is False or (isinstance(result, dict) and result.get("allow") is False):
                    reason = result.get("reason") if isinstance(result, dict) else "工具调用被策略拒绝"
                    raise AgentPolicyDenied(str(reason or "工具调用被策略拒绝"))
            except AgentPolicyDenied:
                raise
            except Exception:
                logger.exception("Agent 策略 Hook 执行失败 hook=%s", getattr(hook, "__name__", type(hook).__name__))


agent_hooks = AgentHookManager()
