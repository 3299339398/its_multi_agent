import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.tools.local.knowledge_base import request_knowledge
from its_multi_agent.backend.app.infrastructure.tools.local.knowledge_base import query_knowledge
from agents.tool_context import ToolContext


class KnowledgeClientAuthTest(unittest.TestCase):
    def test_agent_tool_requests_evidence_without_second_answer_generation(self):
        evidence = {"answer": "", "sources": [{"source_id": "source-1", "excerpt": "Warranty: 36 months"}]}
        with patch(
            "its_multi_agent.backend.app.infrastructure.tools.local.knowledge_base.request_knowledge",
            new=AsyncMock(return_value=evidence),
        ) as request:
            result = asyncio.run(query_knowledge.on_invoke_tool(
                ToolContext(context=None, tool_name="query_knowledge", tool_call_id="test", tool_arguments='{"question":"Warranty?"}'),
                '{"question":"Warranty?"}',
            ))
        self.assertEqual(result, evidence)
        self.assertTrue(request.await_args.kwargs.get("retrieve_only"))

    def test_internal_query_sends_service_token(self):
        token = "service-token-that-is-at-least-32-characters"
        response = MagicMock()
        response.json.return_value = {"answer": "ok"}
        client = AsyncMock()
        client.post.return_value = response
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(settings, "KNOWLEDGE_BASE_URL", "http://knowledge-api:8001/"),
            patch.object(settings, "KNOWLEDGE_SERVICE_TOKEN", token),
            patch(
                "its_multi_agent.backend.app.infrastructure.tools.local.knowledge_base.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            result = asyncio.run(request_knowledge("question"))

        self.assertEqual(result, {"answer": "ok"})
        self.assertEqual(client.post.await_args.kwargs["headers"], {"X-Service-Token": token})
        self.assertEqual(client.post.await_args.kwargs["url"], "http://knowledge-api:8001/query")


if __name__ == "__main__":
    unittest.main()
