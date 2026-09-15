import asyncio
import unittest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pathlib import Path

from its_multi_agent.harness import (
    AgentRunResult, Scenario, grade_result, load_scenarios, run_scenario,
)
from its_multi_agent.harness.real_executor import execute_with_agents
from its_multi_agent.harness import real_executor


class HarnessTest(unittest.TestCase):
    def test_nontext_answers_fail_without_raising(self):
        scenario = Scenario("invalid-answer", "question", must_include=("answer",))
        for answer in (None, 42, ["answer"]):
            with self.subTest(answer=answer):
                result = grade_result(scenario, AgentRunResult(answer))
                self.assertFalse(result.passed)
                self.assertFalse(result.checks["nonempty_answer"])
                self.assertFalse(result.checks["required_content"])

    def test_nontext_content_expectations_fail_without_raising(self):
        for expectation in (None, 42, ["answer"]):
            with self.subTest(expectation=expectation):
                scenario = Scenario("invalid-expectation", "question", must_include=(expectation,))
                result = grade_result(scenario, AgentRunResult("answer"))
                self.assertFalse(result.passed)
                self.assertFalse(result.checks["meaningful_expectations"])
                self.assertFalse(result.checks["required_content"])

    def test_empty_answers_never_pass_even_without_content_expectations(self):
        for answer in ("", " \n\t"):
            result = grade_result(Scenario("empty", "question", expected_tools=("lookup",)),
                                  AgentRunResult(answer, ("lookup",)))
            self.assertFalse(result.passed)

    def test_scenario_without_expectations_is_not_a_passing_evaluation(self):
        result = grade_result(Scenario("unchecked", "question"), AgentRunResult("Anything"))
        self.assertFalse(result.passed)

    def test_forbidden_tools_and_order_are_checked(self):
        scenario = Scenario("ordered", "question", expected_tools=("lookup", "answer"),
                            forbidden_tools=("delete",), expected_tool_order=("lookup", "answer"))
        for calls in (("answer", "lookup"), ("lookup", "delete", "answer")):
            self.assertFalse(grade_result(scenario, AgentRunResult("answer", calls)).passed)
        self.assertTrue(grade_result(scenario, AgentRunResult("answer", ("lookup", "extra", "answer"))).passed)

    def test_blank_content_expectation_is_not_a_meaningful_check(self):
        self.assertFalse(grade_result(Scenario("blank", "question", must_include=("",)),
                                      AgentRunResult("Anything")).passed)

    def test_grounding_expectation_requires_emitted_source_origin(self):
        scenario = Scenario("grounding", "question", expected_source_origins=("knowledge",))
        self.assertFalse(grade_result(scenario, AgentRunResult("Answer")).passed)
        self.assertTrue(grade_result(scenario, AgentRunResult("Answer", sources=(
            {"source_id": "policy-1", "origin": "knowledge"},
        ))).passed)

    def test_grades_expected_tools_and_content(self):
        scenario = Scenario(
            id="case-1", input="找服务站", expected_tools=("service_tool",), must_include=("服务站",)
        )
        result = grade_result(scenario, AgentRunResult("最近的服务站在中关村", ("service_tool",)))
        self.assertTrue(result.passed)
        self.assertEqual(result.checks["expected_tools"], True)

    def test_runner_converts_executor_failure_to_failed_result(self):
        async def broken(_scenario):
            raise RuntimeError("mock unavailable")

        result = asyncio.run(run_scenario(broken, Scenario("case-2", "问题")))
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["no_error"])
        self.assertIn("mock unavailable", result.error)

    def test_loads_repository_scenarios(self):
        path = Path(__file__).with_name("scenarios.json")
        scenarios = load_scenarios(path)
        self.assertEqual([scenario.id for scenario in scenarios], [
            "knowledge-basic-001", "service-station-001", "mixed-routing-001",
        ])


class ProductionAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_service_request_and_sse_trace_preserve_order_sources_and_answer(self):
        requests = []

        class Service:
            @staticmethod
            async def process_task(request, user_id, flag):
                requests.append((request, user_id, flag))
                packets = [
                    {"content": {"kind": "PROCESS", "text": "working"}, "metadata": {"toolName": "lookup"}},
                    {"content": {"kind": "PROCESS", "text": "working"}, "metadata": {"toolName": "lookup", "agentName": "expert"}},
                    {"content": {"contentType": "sagegpt/sources", "sources": [{"source_id": "p1", "origin": "knowledge"}]}},
                    {"content": {"kind": "ANSWER", "text": "Answer [p1]"}},
                    {"content": {"contentType": "sagegpt/finish"}, "status": "FINISHED", "metadata": {"finishReason": "NORMAL"}},
                ]
                stream = "".join("data: " + json.dumps(packet) + "\r\n\r\n" for packet in packets)
                for index in range(0, len(stream), 7):
                    yield stream[index:index + 7]

        scenario = Scenario("service", "question", user_context={"attachment_ids": ["a1"],
                            "enabled_plugins": [], "origin": {"latitude": 39.9, "longitude": 116.4}})
        result = await real_executor.execute_with_service(scenario, service=Service)
        self.assertIsNone(result.error)
        self.assertEqual(result.final_answer, "Answer [p1]")
        self.assertEqual(result.tool_calls, ("lookup", "lookup"))
        self.assertEqual(result.agent_transitions, ("expert",))
        self.assertEqual(result.sources[0]["source_id"], "p1")
        request, user, flag = requests[0]
        self.assertTrue(user.startswith("harness-"))
        self.assertTrue(request.context.session_id.startswith("harness-"))
        self.assertEqual(request.attachment_ids, ["a1"])
        self.assertEqual(request.origin.latitude, 39.9)
        self.assertFalse(flag)
        await real_executor.execute_with_service(scenario, service=Service)
        self.assertNotEqual(requests[0][1], requests[1][1])

    async def test_stream_errors_and_incomplete_streams_fail_with_partial_answer(self):
        for ending in (None, "ERROR", "MAX_TOKENS"):
            class Service:
                @staticmethod
                async def process_task(*args, **kwargs):
                    yield 'data: {"content":{"kind":"ANSWER","text":"partial"}}\n\n'
                    if ending:
                        yield 'data: ' + json.dumps({"content": {"contentType": "sagegpt/finish"},
                            "status": "FINISHED", "metadata": {"finishReason": ending, "errorMessage": "failed"}}) + '\n\n'

            result = await real_executor.execute_with_service(Scenario("error", "question"), service=Service)
            self.assertIsNotNone(result.error)
            self.assertEqual(result.final_answer, "partial")

    async def test_harness_rejects_production_identity(self):
        result = await real_executor.execute_with_service(Scenario("identity", "question", user_context={"user_id": "alice"}))
        self.assertIn("harness-", result.error)

    async def test_real_service_grounding_short_circuit_runs_session_and_attachments(self):
        from its_multi_agent.backend.app.services.agent_service import MultiAgentService
        target = "its_multi_agent.backend.app.services.agent_service."
        grounding = AsyncMock(return_value=SimpleNamespace(route="attachment", status="clarify", sources=[], reply="Which section?"))
        history = [{"role": "user", "content": "question", "attachments": [{"id": "a1"}]}]
        with (
            patch(target + "memory_service.extract_and_store", AsyncMock()),
            patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
            patch(target + "attachment_service.describe", return_value=[{"id": "a1", "kind": "document"}]) as describe,
            patch(target + "attachment_service.prepare_messages", return_value=[{}]),
            patch(target + "attachment_service.prepare_history", return_value=history) as attachment_history,
            patch(target + "session_service.prepare_history", return_value=history) as prepare,
            patch(target + "session_service.save_history") as save,
            patch(target + "resolve_profile", return_value=SimpleNamespace(supports_tools=True)),
            patch(target + "model_for", return_value=object()),
            patch(target + "GroundingWorkflow.prepare", grounding),
            patch(target + "Runner.run_streamed") as generate,
        ):
            result = await real_executor.execute_with_service(Scenario("grounded", "question", user_context={
                "user_id": "harness-test", "session_id": "harness-test", "attachment_ids": ["a1"],
            }), service=MultiAgentService)
        self.assertIsNone(result.error)
        self.assertEqual(result.final_answer, "Which section?")
        describe.assert_called_once_with("harness-test", ["a1"])
        prepare.assert_called_once()
        attachment_history.assert_called_once()
        save.assert_called_once()
        grounding.assert_awaited_once()
        self.assertTrue(grounding.call_args.kwargs["has_attachments"])
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
