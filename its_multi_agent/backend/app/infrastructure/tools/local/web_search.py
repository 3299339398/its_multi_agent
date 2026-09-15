import json
from typing import Any, Dict

from agents import function_tool

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import search_mcp_client
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks, AgentPolicyDenied


async def request_web_search(query: str) -> Dict[str, Any]:
    """Call the configured search MCP and normalize its response."""
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
async def search_web(query: str) -> Dict[str, Any]:
    """Search current public web information such as news, weather, and prices."""
    try:
        await agent_hooks.authorize_tool({"tool_name": "search_web", "query": query})
    except AgentPolicyDenied as error:
        return {"status": "error", "query": query, "error_msg": str(error)}
    return await request_web_search(query)
