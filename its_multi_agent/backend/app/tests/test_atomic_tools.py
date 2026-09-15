import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from its_multi_agent.backend.app.infrastructure.tools.local.web_search import (
    request_web_search,
)
from its_multi_agent.backend.app.plugins import plugin_registry


class AtomicToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_web_search_normalizes_structured_response(self):
        response = SimpleNamespace(
            structuredContent={"items": [{"title": "今日天气"}]},
            content=[],
        )
        with patch(
            "its_multi_agent.backend.app.infrastructure.tools.local.web_search."
            "search_mcp_client.call_tool",
            new=AsyncMock(return_value=response),
        ) as call:
            result = await request_web_search("今天北京天气")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"]["items"][0]["title"], "今日天气")
        call.assert_awaited_once_with("bailian_web_search", {"query": "今天北京天气"})

    async def test_web_search_returns_safe_error(self):
        with patch(
            "its_multi_agent.backend.app.infrastructure.tools.local.web_search."
            "search_mcp_client.call_tool",
            new=AsyncMock(side_effect=RuntimeError("secret provider failure")),
        ):
            result = await request_web_search("新闻")

        self.assertEqual(result["status"], "error")
        self.assertNotIn("secret provider failure", result["error_msg"])

    async def test_mcp_error_payload_is_not_treated_as_search_evidence(self):
        with patch(
            "its_multi_agent.backend.app.infrastructure.tools.local.web_search.search_mcp_client.call_tool",
            AsyncMock(return_value=SimpleNamespace(isError=True, structuredContent={"error": "provider secret"})),
        ):
            result = await request_web_search("今日天气")
        self.assertEqual(result["status"], "error")
        self.assertNotIn("provider secret", str(result))

    def test_plugins_resolve_independent_atomic_tools(self):
        self.assertEqual(
            plugin_registry.resolve_tools(["knowledge"]),
            ["query_knowledge"],
        )
        self.assertEqual(
            plugin_registry.resolve_tools(["search"]),
            ["search_web"],
        )


if __name__ == "__main__":
    unittest.main()
