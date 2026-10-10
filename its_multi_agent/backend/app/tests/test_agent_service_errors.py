from its_multi_agent.backend.app.tests.test_stream_retry_state import FailingModel
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.services.grounding_workflow import GroundingOutcome


async def fake_stream_response(result, include_finish=True, state=None):
    if result.error:
        raise result.error
    if result.chunk:
        if state is not None:
            state.semantic_output = True
        yield result.chunk


def decode_sse(packet: str) -> dict:
    return json.loads(packet.removeprefix("data: ").strip())


class AgentServiceErrorTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_initial_event_retries_but_answer_does_not(self):
        from agents import Agent, Runner
        from its_multi_agent.backend.app.tests.test_stream_retry_state import FailingModel

        for answer, expected_attempts in ((False, 2), (True, 1)):
            with self.subTest(answer=answer):
                agent = Agent(name="test", model=FailingModel(answer=answer))
                real_run = Runner.run_streamed
                with (
                    patch("its_multi_agent.backend.app.services.agent_service.memory_service.extract_and_store", AsyncMock()),
                    patch("its_multi_agent.backend.app.services.agent_service.memory_service.retrieve", AsyncMock(return_value="")),
                    patch("its_multi_agent.backend.app.services.agent_service.session_service.prepare_history", return_value=[{"role": "user", "content": "hello"}]),
                    patch("its_multi_agent.backend.app.services.agent_service.resolve_profile", return_value=SimpleNamespace(supports_tools=True, model_name="offline-test")),
                    patch("its_multi_agent.backend.app.services.agent_service.model_for", return_value=agent.model),
                    patch("its_multi_agent.backend.app.services.agent_service.build_orchestrator_agent", return_value=agent),
                    patch("its_multi_agent.backend.app.services.agent_service.GroundingWorkflow.prepare", AsyncMock(return_value=GroundingOutcome("direct"))),
                    patch("its_multi_agent.backend.app.services.agent_service.Runner.run_streamed", wraps=real_run) as run,
                ):
                    packets = [packet async for packet in MultiAgentService.process_task(self.request, user_id="user-1", flag=True)]
                self.assertEqual(run.call_count, expected_attempts)
                self.assertEqual(decode_sse(packets[-1])["metadata"]["finishReason"], "ERROR")

    def setUp(self):
        self.request = ChatMessageRequest(
            query="测试问题",
            context=UserContext(session_id="session-1"),
            model_profile_id="test-model",
        )

    async def test_retry_does_not_repeat_request_side_effects(self):
        failed = SimpleNamespace(error=ConnectionError("temporary"), chunk="", final_output=None)
        succeeded = SimpleNamespace(error=None, chunk="data: partial\n\n", final_output="完成")
        extract = AsyncMock(return_value=None)
        retrieve = AsyncMock(return_value="")
        prepare = MagicMock(return_value=[{"role": "user", "content": "测试问题"}])

        with (
            patch("its_multi_agent.backend.app.services.agent_service.memory_service.extract_and_store", extract),
            patch("its_multi_agent.backend.app.services.agent_service.memory_service.retrieve", retrieve),
            patch("its_multi_agent.backend.app.services.agent_service.session_service.prepare_history", prepare),
            patch("its_multi_agent.backend.app.services.agent_service.session_service.save_history"),
            patch("its_multi_agent.backend.app.services.agent_service.resolve_profile", return_value=SimpleNamespace(supports_tools=True, model_name="offline-test")),
            patch("its_multi_agent.backend.app.services.agent_service.model_for", return_value=FailingModel()),
            patch("its_multi_agent.backend.app.services.agent_service.build_orchestrator_agent", return_value=object()),
            patch("its_multi_agent.backend.app.services.agent_service.GroundingWorkflow.prepare", AsyncMock(return_value=GroundingOutcome("direct"))),
            patch("its_multi_agent.backend.app.services.agent_service.Runner.run_streamed", side_effect=[failed, succeeded]) as run,
            patch("its_multi_agent.backend.app.services.agent_service.process_stream_response", new=fake_stream_response),
            patch("its_multi_agent.backend.app.services.agent_service.asyncio.create_task", side_effect=lambda coro: coro.close()),
        ):
            packets = [packet async for packet in MultiAgentService.process_task(
                self.request, user_id="user-1", flag=True
            )]

        self.assertEqual(run.call_count, 2)
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(retrieve.await_count, 1)
        self.assertEqual(extract.await_args_list[0].args[3], "")
        self.assertEqual(sum(call.args[3] == "" for call in extract.await_args_list), 1)
        self.assertEqual(decode_sse(packets[-1])["metadata"]["finishReason"], "NORMAL")

    async def test_failure_has_visible_answer_and_error_finish_packet(self):
        with (
            patch("its_multi_agent.backend.app.services.agent_service.memory_service.extract_and_store", AsyncMock()),
            patch("its_multi_agent.backend.app.services.agent_service.memory_service.retrieve", AsyncMock(return_value="")),
            patch("its_multi_agent.backend.app.services.agent_service.session_service.prepare_history", return_value=[]),
            patch("its_multi_agent.backend.app.services.agent_service.resolve_profile", side_effect=ValueError("未知模型配置")),
        ):
            packets = [packet async for packet in MultiAgentService.process_task(
                self.request, user_id="user-1", flag=True
            )]

        answer = decode_sse(packets[0])
        finish = decode_sse(packets[1])
        self.assertEqual(answer["content"]["kind"], "ANSWER")
        self.assertIn("模型配置无效", answer["content"]["text"])
        self.assertEqual(finish["status"], "FINISHED")
        self.assertEqual(finish["metadata"]["finishReason"], "ERROR")
        self.assertIn("模型配置无效", finish["metadata"]["errorMessage"])


if __name__ == "__main__":
    unittest.main()
