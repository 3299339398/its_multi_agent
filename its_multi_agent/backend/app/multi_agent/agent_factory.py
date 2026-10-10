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
from its_multi_agent.backend.app.infrastructure.tools.local.code_workspace import CODE_TOOLS
from its_multi_agent.backend.app.infrastructure.tools.local.service_station import (
    resolve_user_location_from_text,
    query_nearest_repair_shops_by_coords,
)
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.schemas.service_agent import ServiceAgentResult, ServiceTask
from its_multi_agent.backend.app.services.agent_hooks import (
    agent_hooks, expand_allowed_tools, expand_confirmed_tools, tool_allowed, tool_confirmed,
)
from its_multi_agent.backend.app.multi_agent.service_agent import build_service_agent


def normalize_service_task(value: str, navigation_task: ServiceTask | None = None) -> str:
    """将主 Agent 的委派内容转换为专业子任务契约。"""
    raw = str(value or "").strip()
    if not raw:
        raw = "请说明需要查询的服务站、地点或路线任务"
    try:
        task = ServiceTask.model_validate_json(raw)
    except (ValueError, ValidationError):
        # 兼容旧版主 Agent 直接传递纯文本的调用方式。
        task = ServiceTask(request=raw)
    if navigation_task is not None:
        # 从会话恢复的位置参数优先于不完整或颠倒的委派内容，
        # 同时保留品牌、维修类型等专业字段。
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
    """专业子 Agent 未遵守 JSON 结果契约时返回受控失败。"""
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
    """创建当前请求专用、并绑定所选专业模型的工具。"""

    @function_tool
    async def query_service_station_and_navigate(
        ctx: RunContextWrapper[AgentRequestContext], query: str,
    ) -> str:
        """通过服务专家执行范围受限的 JSON 子任务。"""
        if not tool_allowed(ctx.context, "query_service_station_and_navigate"):
            return ServiceAgentResult(
                status="unavailable",
                error="当前分支未启用地图与服务站工具",
            ).model_dump_json(ensure_ascii=False)
        if not tool_confirmed(ctx.context, "query_service_station_and_navigate"):
            return ServiceAgentResult(
                status="unavailable",
                error="地图与服务站操作尚未获得用户确认",
            ).model_dump_json(ensure_ascii=False)
        try:
            await agent_hooks.authorize_tool({
                "tool_name": "query_service_station_and_navigate",
                "user_id": ctx.context.user_id,
                "run_id": ctx.context.run_id,
                "context": ctx.context,
            })
            from dataclasses import replace
            service_context = replace(
                ctx.context,
                allowed_tools=expand_allowed_tools(ctx.context.allowed_tools),
                confirmed_tools=expand_confirmed_tools(ctx.context.confirmed_tools),
            )
            worker = service_agent
            if worker is None:
                # 保持工具工厂可独立使用；正式请求会传入当前请求选定的模型。
                worker = build_service_agent(context=service_context)
            else:
                # 保留父 Agent 的模型、输出预算和提示词，仅替换请求范围的 MCP 权限视图。
                from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import map_mcp_client_for
                worker = worker.clone(mcp_servers=[map_mcp_client_for(service_context)])

            result = await Runner.run(
                worker,
                input=normalize_service_task(query, ctx.context.navigation_task),
                context=service_context,
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
        *CODE_TOOLS,
    ]
    if enabled_tools is None:
        return tools
    allowed = set(enabled_tools)
    return [tool for tool in tools if getattr(tool, "name", None) in allowed]


def fork_toolset(service_agent=None) -> tuple:
    """返回固定顺序的 Fork 工具集合；权限由运行时上下文再做校验。

    服务编排工具是 ``build_agent_tools`` 创建的闭包，必须在同一工厂内创建，
    这样它才能持有当前请求选定的业务模型，同时保持父、子 Agent 的工具顺序一致。
    """
    tools = build_agent_tools(service_agent)
    # 主编排工具排在前面，服务专家的原子工具紧随其后，工程工具保持最后的稳定顺序。
    return tuple((*tools[:3], resolve_user_location_from_text,
                  query_nearest_repair_shops_by_coords, *tools[3:]))
