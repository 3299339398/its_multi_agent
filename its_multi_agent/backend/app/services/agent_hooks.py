"""Agent 运行生命周期钩子。

观察型钩子的异常只记录日志，不中断用户请求。
工具策略钩子可通过明确的拒绝结果阻止工具执行。
"""
from its_multi_agent.backend.app.repositories.sqlite_task_repository import execution_lease, task_repository
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any

from its_multi_agent.backend.app.schemas.tool import ToolPolicyDecision

logger = logging.getLogger(__name__)

Hook = Callable[[dict[str, Any]], Any]


class AgentPolicyDenied(PermissionError):
    """工具策略拒绝执行或授权策略故障时抛出此异常。"""


CONFIRMATION_REQUIRED_TOOLS = frozenset({
    "query_service_station_and_navigate",
    "resolve_user_location_from_text",
    "query_nearest_repair_shops_by_coords",
    "create_file",
    "list_code_files",
    "read_code_file",
    "search_code",
    "replace_code",
    "create_code_file",
    "run_code_check",
})

MAP_TOOL_NAMES = frozenset({
    "query_service_station_and_navigate",
    "resolve_user_location_from_text",
    "query_nearest_repair_shops_by_coords",
    "map_search_places", "map_geocode", "map_directions",
    "map_directions_matrix", "map_uri",
})

_TOOL_POLICY_METADATA = {
    "query_knowledge": ("low", "read"),
    "search_web": ("low", "read"),
    "resolve_user_location_from_text": ("high", "external"),
    "query_nearest_repair_shops_by_coords": ("high", "external"),
    "query_service_station_and_navigate": ("high", "external"),
    "map_search_places": ("high", "external"),
    "map_geocode": ("high", "external"),
    "map_directions": ("high", "external"),
    "map_directions_matrix": ("high", "external"),
    "map_uri": ("high", "external"),
    "create_file": ("high", "write"),
    "list_code_files": ("high", "read"),
    "read_code_file": ("high", "read"),
    "search_code": ("high", "read"),
    "replace_code": ("high", "write"),
    "create_code_file": ("high", "write"),
    "run_code_check": ("high", "write"),
}


def expand_confirmed_tools(confirmed_tools):
    """把地图插件的父编排确认传播到其本地/MCP子工具。"""
    confirmed = set(confirmed_tools or ())
    if "query_service_station_and_navigate" in confirmed:
        confirmed.update(MAP_TOOL_NAMES)
    return frozenset(confirmed)


def expand_allowed_tools(allowed_tools):
    """把已启用的地图编排工具展开为其受限的地图子工具。"""
    allowed = set(allowed_tools or ())
    if "query_service_station_and_navigate" in allowed:
        allowed.update(MAP_TOOL_NAMES)
    return frozenset(allowed)


def evaluate_tool(context, tool_name: str) -> ToolPolicyDecision:
    """统一计算工具权限、确认状态和副作用等级。"""
    risk_level, side_effect_level = _TOOL_POLICY_METADATA.get(
        tool_name, ("medium", "external"),
    )
    allowed = tool_name in expand_allowed_tools(
        getattr(context, "allowed_tools", frozenset())
    )
    requires_confirmation = tool_name in CONFIRMATION_REQUIRED_TOOLS | MAP_TOOL_NAMES
    confirmed = (not requires_confirmation) or tool_name in expand_confirmed_tools(
        getattr(context, "confirmed_tools", frozenset())
    )
    if not allowed:
        reason = "工具不在当前请求或分支白名单中"
    elif not confirmed:
        reason = "工具需要本次请求的用户确认"
    else:
        reason = "允许执行"
    return ToolPolicyDecision(
        tool_name=tool_name,
        allowed=allowed,
        confirmed=confirmed,
        risk_level=risk_level,
        side_effect_level=side_effect_level,
        reason=reason,
    )


def _audit_policy_decision(context, decision: ToolPolicyDecision) -> None:
    """记录不含工具参数和结果的策略审计摘要。"""
    audit = {
            "user_id": getattr(context, "user_id", None),
            "project_id": getattr(context, "project_id", None),
            "run_id": getattr(context, "run_id", None),
            "tool_name": decision.tool_name,
            "allowed": decision.allowed,
            "confirmed": decision.confirmed,
            "permitted": decision.permitted,
            "risk_level": decision.risk_level,
            "side_effect_level": decision.side_effect_level,
            "reason": decision.reason,
    }
    logger.info("[ToolPolicy] %s", json.dumps(audit, ensure_ascii=False, separators=(",", ":")))
    if not audit["user_id"] and not audit["run_id"]:
        return
    try:
        task_repository.append_tool_audit(audit)
    except Exception:
        # 审计存储故障不能改变当前工具的授权结果，但必须留下可检索日志。
        logger.exception("工具策略审计写入失败 tool=%s", decision.tool_name)


def tool_allowed(context, tool_name: str) -> bool:
    """检查请求/分支白名单；缺少白名单时默认拒绝。"""
    decision = evaluate_tool(context, tool_name)
    if not decision.allowed:
        _audit_policy_decision(context, decision)
    return decision.allowed


def tool_confirmed(context, tool_name: str) -> bool:
    """检查高风险工具是否有本次请求的用户确认。"""
    decision = evaluate_tool(context, tool_name)
    if not decision.confirmed:
        _audit_policy_decision(context, decision)
    return decision.confirmed


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
        # 遍历回调快照，允许钩子在处理事件时注销自身。
        for hook in tuple(self._hooks[event]):
            try:
                result = hook(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Agent Hook 执行失败 event=%s hook=%s", event, getattr(hook, "__name__", type(hook).__name__))

    async def authorize_tool(self, payload: dict[str, Any]) -> None:
        """执行策略钩子；拒绝结果和策略异常都阻止工具调用。"""
        lease = execution_lease.get()
        if lease:
            task_repository.assert_execution_lease(lease[0])
        context = payload.get("context")
        if context is not None:
            decision = evaluate_tool(context, str(payload.get("tool_name", "")))
            _audit_policy_decision(context, decision)
            if not decision.permitted:
                raise AgentPolicyDenied(decision.reason)
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
            except Exception as error:
                logger.exception("Agent 策略 Hook 执行失败 hook=%s", getattr(hook, "__name__", type(hook).__name__))
                raise AgentPolicyDenied("工具授权策略暂时不可用") from error

    def authorize_tool_sync(self, payload: dict[str, Any]) -> None:
        """为阻塞式函数工具执行同步策略检查。"""
        lease = execution_lease.get()
        if lease:
            task_repository.assert_execution_lease(lease[0])
        context = payload.get("context")
        if context is not None:
            decision = evaluate_tool(context, str(payload.get("tool_name", "")))
            _audit_policy_decision(context, decision)
            if not decision.permitted:
                raise AgentPolicyDenied(decision.reason)
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
            except Exception as error:
                logger.exception("Agent 策略 Hook 执行失败 hook=%s", getattr(hook, "__name__", type(hook).__name__))
                raise AgentPolicyDenied("工具授权策略暂时不可用") from error


agent_hooks = AgentHookManager()
