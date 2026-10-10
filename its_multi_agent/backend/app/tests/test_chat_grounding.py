from its_multi_agent.backend.app.tests.test_stream_retry_state import FailingModel
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.services.grounding_workflow import GroundingWorkflow, EvidenceReview


class ChatGroundingTest(unittest.IsolatedAsyncioTestCase):
    async def run_chat(self, payload, review=None):
        target = "its_multi_agent.backend.app.services.agent_service."
        history = [{"role": "user", "content": "公司最新差旅制度是什么？"}]
        workflow = GroundingWorkflow(object())
        workflow.review = AsyncMock(return_value=review)
        agent = SimpleNamespace(instructions="base instructions")
        result = SimpleNamespace(final_output="住宿标准为 500 元。[policy-1]", cancel=lambda: None)

        async def stream(_result, **kwargs):
            yield 'data: {"content":{"text":"住宿标准为 500 元。[policy-1]"}}\n\n'

        with (
            patch(target + "memory_service.extract_and_store", AsyncMock()),
            patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
            patch(target + "session_service.prepare_history", return_value=history),
            patch(target + "session_service.save_history") as save,
            patch(target + "resolve_profile", return_value=SimpleNamespace(supports_tools=True, model_name="offline-test")),
            patch(target + "model_for", return_value=FailingModel()),
            patch(target + "GroundingWorkflow", return_value=workflow, create=True),
            patch(target + "build_orchestrator_agent", return_value=agent) as build,
            patch(target + "Runner.run_streamed", return_value=result) as generate,
            patch(target + "process_stream_response", stream),
            patch(target + "asyncio.create_task", side_effect=lambda coro: coro.close()),
            patch("its_multi_agent.backend.app.services.grounding_workflow.request_knowledge", AsyncMock(return_value=payload)),
        ):
            packets = [json.loads(packet.removeprefix("data: ")) async for packet in MultiAgentService.process_task(
                ChatMessageRequest(query="公司最新差旅制度是什么？", context=UserContext(session_id="s")),
                user_id="alice", flag=False,
            )]
        return packets, save, build, generate

    async def test_insufficient_evidence_reply_is_archived_without_answer_generation(self):
        packets, save, build, generate = await self.run_chat({"sources": []})
        generate.assert_not_called()
        self.assertEqual(packets[-1]["metadata"]["finishReason"], "NORMAL")
        archived = save.call_args.args[2][-1]
        self.assertEqual(archived["role"], "assistant")
        self.assertIn("不足", archived["content"])

    async def test_reviewed_evidence_reaches_model_but_not_archive(self):
        evidence = {"sources": [{"source_id": "policy-1", "source_name": "差旅制度", "excerpt": "住宿标准为 500 元。"}]}
        packets, save, build, generate = await self.run_chat(evidence, EvidenceReview(
            status="sufficient", supporting_source_ids=["policy-1"], missing_information="",
        ))
        self.assertEqual(build.call_args.kwargs["enabled_tools"], [])
        model_input = generate.call_args.kwargs["input"]
        self.assertIn("retrieved_evidence", json.dumps(model_input))
        self.assertNotIn("retrieved_evidence", json.dumps(save.call_args.args[2]))
        self.assertEqual(packets[-1]["metadata"]["finishReason"], "NORMAL")

    async def test_sources_arrive_before_answer_and_are_archived_with_it(self):
        evidence = {"sources": [{"source_id": "policy-1", "source_name": "差旅制度", "excerpt": "住宿标准为 500 元。", "page": 2}]}
        packets, save, _build, _generate = await self.run_chat(evidence, EvidenceReview(
            status="sufficient", supporting_source_ids=["policy-1"], missing_information="",
        ))
        source_packets = [packet for packet in packets if packet["content"].get("contentType") == "sagegpt/sources"]
        self.assertEqual(len(source_packets), 1)
        self.assertEqual(source_packets[0]["content"]["sources"][0]["excerpt"], "住宿标准为 500 元。")
        self.assertLess(packets.index(source_packets[0]), next(index for index, packet in enumerate(packets)
                        if packet["content"].get("text", "").startswith("住宿标准")))
        self.assertEqual(save.call_args.args[2][-1].get("sources", [{}])[0].get("page"), 2)


if __name__ == "__main__":
    unittest.main()
