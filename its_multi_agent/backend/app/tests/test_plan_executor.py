import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from its_multi_agent.backend.app.schemas.task_plan import TaskPlan, StepReview
from its_multi_agent.backend.app.services.plan_executor import PlanExecutor, StepBlocked, needs_plan
from its_multi_agent.backend.app.services.grounding_workflow import GroundingOutcome
from its_multi_agent.backend.app.schemas.agent_context import AgentRequestContext
from its_multi_agent.backend.app.utils.response_util import ResponseFactory


def plan(executor="technical"):
    return TaskPlan(summary="分步分析", steps=[
        dict(id="step-1", title="分析", executor=executor, task="解释递归", success_criteria="解释原理"),
        dict(id="step-2", title="举例", executor="technical", task="给出递归例子",
             depends_on=["step-1"], success_criteria="提供例子"),
    ])


class PlanTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.worker = PlanExecutor(object(), AgentRequestContext("alice", "s"), [])
        self.patcher = patch("its_multi_agent.backend.app.services.plan_executor.PlanningAgent.plan", AsyncMock(return_value=plan()))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_dependencies_and_arbitrary_executor_are_rejected(self):
        for mutation in ({"depends_on": ["step-2"]}, {"executor": "terminal"}, {"id": "step-2"}):
            raw = plan().model_dump()
            raw["steps"][0].update(mutation)
            with self.assertRaises(ValidationError):
                TaskPlan.model_validate(raw)

    async def test_failed_dependency_skips_without_executing(self):
        self.worker.execute = AsyncMock(side_effect=StepBlocked("缺少资料"))
        events = [e async for e in self.worker.run("先解释递归，再举例", [])]
        self.assertEqual([r["status"] for r in events[-1]["steps"]], ["blocked", "skipped"])
        self.worker.execute.assert_awaited_once()
        self.assertEqual(events[-1]["status"], "failed")
        # Earlier emitted snapshots must not change after execution.
        self.assertEqual(events[1]["steps"][0]["status"], "pending")

    async def test_disabled_service_is_rejected_before_execution(self):
        with patch("its_multi_agent.backend.app.services.plan_executor.PlanningAgent.plan", AsyncMock(return_value=plan("service"))):
            self.worker.execute = AsyncMock()
            events = [e async for e in self.worker.run("分步执行", [])]
        self.worker.execute.assert_not_awaited()
        self.assertEqual(events[-1]["status"], "failed")

    async def test_reviewer_rejects_incomplete_result(self):
        self.worker.execute = AsyncMock(return_value="未完成")
        with patch("its_multi_agent.backend.app.services.plan_executor.GroundingWorkflow._structured", AsyncMock(return_value=StepReview(complete=False, missing="缺少例子"))):
            events = [e async for e in self.worker.run("分步执行", [])]
        self.assertEqual(events[-1]["steps"][0]["status"], "blocked")

    async def test_cancel_propagates_and_does_not_start_next_step(self):
        self.worker.execute = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            _ = [e async for e in self.worker.run("分步执行", [])]
        self.worker.execute.assert_awaited_once()

    async def test_completed_plan_produces_wire_compatible_events(self):
        self.worker.execute = AsyncMock(return_value="已解释并举例")
        with patch("its_multi_agent.backend.app.services.plan_executor.GroundingWorkflow._structured", AsyncMock(return_value=StepReview(complete=True))):
            events = [json.loads(ResponseFactory.build_plan(e).model_dump_json()) async for e in self.worker.run("分步执行", [])]
        self.assertEqual(events[-1]["content"]["contentType"], "sagegpt/plan")
        self.assertEqual(events[-1]["content"]["status"], "completed")

    async def test_no_web_constraint_reaches_every_research_step(self):
        self.worker.tools.add("search_web")
        with patch("its_multi_agent.backend.app.services.plan_executor.GroundingWorkflow.prepare", AsyncMock(return_value=GroundingOutcome("knowledge", "unavailable", reply="禁用"))) as prepare:
            with self.assertRaises(StepBlocked):
                await self.worker.execute(plan("research").steps[0], "不要联网", [], False, [])
        self.assertIn("不要联网", prepare.await_args.args[0])

    def test_simple_chat_does_not_plan(self):
        self.assertFalse(needs_plan("你好"))
        self.assertFalse(needs_plan("你是哪个模型"))
        self.assertTrue(needs_plan("先解释递归，再举例"))

    async def test_partial_success_keeps_independent_work(self):
        raw = plan().model_dump()
        raw["steps"][1]["depends_on"] = []
        self.worker.execute = AsyncMock(side_effect=[StepBlocked("缺少条件"), "完成例子"])
        with (
            patch("its_multi_agent.backend.app.services.plan_executor.PlanningAgent.plan", AsyncMock(return_value=TaskPlan.model_validate(raw))),
            patch("its_multi_agent.backend.app.services.plan_executor.GroundingWorkflow._structured", AsyncMock(return_value=StepReview(complete=True))),
        ):
            events = [e async for e in self.worker.run("分步执行", [])]
        self.assertEqual(events[-1]["status"], "partial")
        self.assertEqual([r["status"] for r in events[-1]["steps"]], ["blocked", "completed"])


class PlanApiTest(unittest.TestCase):
    def test_failed_plan_stream_has_error_finish_without_answer_generation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from its_multi_agent.backend.app.api.routers import router
        from its_multi_agent.backend.app.api.dependencies import get_current_user
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "test", "username": "test"}
        target = "its_multi_agent.backend.app.services.agent_service."
        with (
            patch(target + "memory_service.extract_and_store", AsyncMock()),
            patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
            patch(target + "session_service.prepare_history", return_value=[{"role": "user", "content": "分步执行"}]),
            patch(target + "session_service.save_history") as save,
            patch(target + "model_for", return_value=object()),
            patch("its_multi_agent.backend.app.services.plan_executor.PlanningAgent.plan", AsyncMock(side_effect=ValueError("private provider error"))),
            patch(target + "Runner.run_streamed") as generate,
            TestClient(app) as client,
        ):
            response = client.post("/api/query", json={"query": "分步执行", "context": {"session_id": "test"}})
        packets = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(packets[-1]["metadata"]["finishReason"], "ERROR")
        self.assertNotIn("private provider error", response.text)
        self.assertTrue(any(p.get("content", {}).get("status") == "failed" for p in packets))
        generate.assert_not_called()
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
