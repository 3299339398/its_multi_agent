"""采集实际聊天服务的 SSE 契约数据，覆盖证据审查流程。

采用延迟导入，使确定性评分无需配置模型服务。
工具轨迹仅包含主 Agent 发出的事件，不包含证据审查阶段的检索调用。
"""

import json
import re
import time
from uuid import uuid4

from .models import AgentRunResult, Scenario


async def execute_with_service(scenario: Scenario, *, service=None) -> AgentRunResult:
    """使用隔离的评测用户身份和会话执行聊天请求。"""
    started = time.perf_counter()
    answer: list[str] = []
    tool_calls: list[str] = []
    transitions: list[str] = []
    sources: list[dict] = []
    plan_executors: list[str] = []
    grounding_trace: list[dict] = []
    error = None
    finished = False
    first_event_latency_ms = 0.0
    route = None
    # PROCESS tool names are dispatch observations, not committed effects.
    # Until an operation/result audit adapter supplies evidence, this is unknown.
    duplicate_side_effects = None

    def consume(frame: str):
        nonlocal finished, error, first_event_latency_ms, route, duplicate_side_effects
        if first_event_latency_ms <= 0:
            first_event_latency_ms = (time.perf_counter() - started) * 1000
        data = "\n".join(line[5:].lstrip(" ") for line in frame.splitlines() if line.startswith("data:"))
        if not data:
            return
        packet = json.loads(data)
        content, metadata = packet.get("content", {}), packet.get("metadata", {})
        if finished:
            raise ValueError("SSE data received after finish")
        if content.get("kind") == "ANSWER":
            answer.append(content.get("text", ""))
        if content.get("kind") == "PROCESS":
            if metadata.get("toolName"):
                tool = metadata["toolName"]
                tool_calls.append(tool)
            if metadata.get("agentName"):
                transitions.append(metadata["agentName"])
        if content.get("contentType") == "sagegpt/sources":
            sources.extend(content.get("sources", []))
        if content.get("contentType") == "sagegpt/plan":
            for step in content.get("steps", []):
                executor = step.get("executor")
                if executor and executor not in plan_executors:
                    plan_executors.append(executor)
        if content.get("contentType") == "sagegpt/grounding-trace":
            grounding_trace.append(content)
            route = content.get("route") or route
        if content.get("contentType") == "sagegpt/plan":
            route = route or "plan"
        if packet.get("status") == "FINISHED":
            finished = True
            if metadata.get("finishReason") != "NORMAL":
                error = metadata.get("errorMessage") or f"Stream finished: {metadata.get('finishReason')}"

    try:
        context = dict(scenario.user_context)
        allowed = {
            "user_id", "session_id", "origin", "flag", "model_profile_id",
            "enabled_plugins", "confirmed_plugins", "project_id", "work_mode",
            "attachment_ids", "temporary_model",
        }
        if context.keys() - allowed:
            raise ValueError(f"unsupported harness context fields: {sorted(context.keys() - allowed)}")
        user_id = context.pop("user_id", "harness-" + uuid4().hex)
        session_id = context.pop("session_id", "harness-" + uuid4().hex)
        flag = context.pop("flag", False)
        project_id = context.pop("project_id", "default")
        work_mode = context.pop("work_mode", "auto")
        confirmed_plugins = context.pop("confirmed_plugins", [])
        for value in (user_id, session_id):
            if not isinstance(value, str) or not re.fullmatch(r"harness-[A-Za-z0-9_-]{1,120}", value):
                raise ValueError("harness user_id and session_id must start with harness- and use letters, digits, _ or -")
        from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext

        request = ChatMessageRequest(
            query=scenario.input,
            context=UserContext(session_id=session_id),
            flag=flag,
            project_id=project_id,
            work_mode=work_mode,
            confirmed_plugins=confirmed_plugins,
            **context,
        )
        if service is None:
            from its_multi_agent.backend.app.services.agent_service import MultiAgentService
            service = MultiAgentService
        buffer = ""
        async for chunk in service.process_task(request, user_id=user_id, flag=request.flag):
            buffer += chunk
            while match := re.search(r"\r?\n\r?\n", buffer):
                frame, buffer = buffer[:match.start()], buffer[match.end():]
                consume(frame)
        if buffer.strip():
            raise ValueError("Incomplete SSE packet")
        if not finished:
            raise ValueError("Stream ended without a finish packet")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return AgentRunResult(
        final_answer="".join(answer), tool_calls=tuple(tool_calls), agent_transitions=tuple(transitions),
        latency_ms=(time.perf_counter() - started) * 1000, error=error, sources=tuple(sources),
        plan_executors=tuple(plan_executors),
        grounding_trace=tuple(grounding_trace),
        route=route,
        first_event_latency_ms=first_event_latency_ms,
        duplicate_side_effects=duplicate_side_effects,
    )


async def execute_with_agents(scenario: Scenario) -> AgentRunResult:
    """保留实际聊天服务适配器的兼容入口。"""
    return await execute_with_service(scenario)
