import json
import re

from agents import Runner, RunContextWrapper, function_tool
from agents.run import RunConfig
from pydantic import ValidationError

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.tools.local.knowledge_base import (
    query_knowledge,
)
from its_multi_agent.backend.app.infrastructure.tools.local.web_search import search_web
from its_multi_agent.backend.app.infrastructure.tools.local.file_output import create_file
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.schemas.service_agent import ServiceAgentResult, ServiceTask


def normalize_service_task(value: str, navigation_task: ServiceTask | None = None) -> str:
    """Convert the orchestrator's handoff into the specialist task contract."""
    raw = str(value or "").strip()
    if not raw:
        raw = "请说明需要查询的服务站、地点或路线任务"
    try:
        task = ServiceTask.model_validate_json(raw)
    except (ValueError, ValidationError):
        # Keep compatibility with older orchestrator calls that sent plain text.
        task = ServiceTask(request=raw)
    if navigation_task is not None:
        # Session-derived slots take precedence over an incomplete or reversed
        # handoff. Keep specialist-only fields such as brand and repair type.
        task = task.model_copy(update={
            "request": navigation_task.request,
            "origin_hint": navigation_task.origin_hint,
            "destination_hint": navigation_task.destination_hint,
            "transport_mode": navigation_task.transport_mode,
            "needs_navigation": True,
            "constraints": list(dict.fromkeys(navigation_task.constraints + task.constraints))[:8],
        })
    return task.model_dump_json(ensure_ascii=False)


def normalize_service_result(value) -> str:
    """Fail closed when the specialist does not honor its JSON result contract."""
    try:
        if isinstance(value, ServiceAgentResult):
            result = value
        elif isinstance(value, dict):
            result = ServiceAgentResult.model_validate(value)
        else:
            raw = str(value or "").strip()
            if raw.startswith("```"):
                raw = re.sub(
                    r"^```(?:json)?\s*|\s*```$", "", raw,
                    flags=re.IGNORECASE | re.DOTALL,
                ).strip()
            result = ServiceAgentResult.model_validate(json.loads(raw))
        if result.status == "ok" and not (result.summary or result.stations or result.route):
            raise ValueError("successful service result has no usable content")
    except (ValueError, TypeError, json.JSONDecodeError, ValidationError):
        logger.warning("业务专家返回了无效的结构化结果")
        result = ServiceAgentResult(
            status="unavailable",
            error="业务专家返回结果格式无效",
        )
    return result.model_dump_json(ensure_ascii=False)


def build_agent_tools(service_agent, enabled_tools=None):
    """Create request-scoped tools bound to the selected specialist models."""

    @function_tool
    async def query_service_station_and_navigate(
        ctx: RunContextWrapper[AgentRequestContext], query: str,
    ) -> str:
        """Run a bounded JSON task through the service specialist."""
        try:
            result = await Runner.run(
                service_agent,
                input=normalize_service_task(query, ctx.context.navigation_task),
                context=ctx.context,
                run_config=RunConfig(tracing_disabled=True),
            )
            return normalize_service_result(result.final_output)
        except Exception:
            logger.exception("业务专家执行失败")
            return ServiceAgentResult(
                status="unavailable",
                error="业务专家暂时无法回答，请稍后重试",
            ).model_dump_json(ensure_ascii=False)

    tools = [
        query_knowledge,
        search_web,
        query_service_station_and_navigate,
        create_file,
    ]
    if enabled_tools is None:
        return tools
    allowed = set(enabled_tools)
    return [tool for tool in tools if getattr(tool, "name", None) in allowed]
