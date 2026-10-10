import json
from typing import Any, Dict

from agents import RunContextWrapper, function_tool

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import search_mcp_client
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks, AgentPolicyDenied
from its_multi_agent.backend.app.services.agent_hooks import tool_allowed
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.schemas.tool import WebSearchToolRequest


async def request_web_search(query: str) -> Dict[str, Any]:
    """调用已配置的搜索 MCP，并规范化响应结果。"""
    try:
        result = await search_mcp_client.call_tool(
            "bailian_web_search", {"query": query}
        )
        if getattr(result, "isError", False):
            return {"status": "error", "query": query, "error_msg": "联网搜索服务暂时不可用"}
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return {"status": "ok", "query": query, "results": structured}

        items: list[Any] = []
        for content in getattr(result, "content", []):
            text = getattr(content, "text", None)
            if not text:
                continue
            try:
                items.append(json.loads(text))
            except (TypeError, json.JSONDecodeError):
                items.append(text)
        return {"status": "ok", "query": query, "results": items}
    except Exception as error:
        logger.error("联网搜索失败: %s", error)
        return {
            "status": "error",
            "query": query,
            "error_msg": "联网搜索服务暂时不可用",
        }


@function_tool
async def search_web(ctx: RunContextWrapper[AgentRequestContext], query: str) -> Dict[str, Any]:
    """搜索新闻、天气和价格等公开的实时网络信息。"""
    if not tool_allowed(ctx.context, "search_web"):
        return {"status": "error", "query": query, "error_msg": "当前分支未启用联网搜索"}
    try:
        request = WebSearchToolRequest(query=query)
    except Exception:
        return {"status": "error", "query": query, "error_msg": "联网搜索参数无效"}
    try:
        await agent_hooks.authorize_tool({
            "tool_name": "search_web", "query": request.query, "context": ctx.context,
        })
    except AgentPolicyDenied as error:
        return {"status": "error", "query": query, "error_msg": str(error)}
    return await request_web_search(request.query)
