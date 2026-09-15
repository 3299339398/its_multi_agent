"""Capture the production chat service SSE contract, including grounding.

Imports remain lazy so deterministic grading needs no provider configuration.
Tool traces include only emitted orchestrator events, not grounding retrieval.
"""

import json
import re
import time
from uuid import uuid4

from .models import AgentRunResult, Scenario


async def execute_with_service(scenario: Scenario, *, service=None) -> AgentRunResult:
    """Run a chat request under an isolated harness identity and session."""
    started = time.perf_counter()
    answer: list[str] = []
    tool_calls: list[str] = []
    transitions: list[str] = []
    sources: list[dict] = []
    error = None
    finished = False

    def consume(frame: str):
        nonlocal finished, error
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
                tool_calls.append(metadata["toolName"])
            if metadata.get("agentName"):
                transitions.append(metadata["agentName"])
        if content.get("contentType") == "sagegpt/sources":
            sources.extend(content.get("sources", []))
        if packet.get("status") == "FINISHED":
            finished = True
            if metadata.get("finishReason") != "NORMAL":
                error = metadata.get("errorMessage") or f"Stream finished: {metadata.get('finishReason')}"

    try:
        context = dict(scenario.user_context)
        allowed = {"user_id", "session_id", "origin", "flag", "model_profile_id", "enabled_plugins",
                   "attachment_ids", "temporary_model"}
        if context.keys() - allowed:
            raise ValueError(f"unsupported harness context fields: {sorted(context.keys() - allowed)}")
        user_id = context.pop("user_id", "harness-" + uuid4().hex)
        session_id = context.pop("session_id", "harness-" + uuid4().hex)
        for value in (user_id, session_id):
            if not isinstance(value, str) or not re.fullmatch(r"harness-[A-Za-z0-9_-]{1,120}", value):
                raise ValueError("harness user_id and session_id must start with harness- and use letters, digits, _ or -")
        from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext

        request = ChatMessageRequest(query=scenario.input, context=UserContext(session_id=session_id),
                                     **{**context, "flag": context.get("flag", False)})
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
    )


async def execute_with_agents(scenario: Scenario) -> AgentRunResult:
    """Backward-compatible name for the production service adapter."""
    return await execute_with_service(scenario)
