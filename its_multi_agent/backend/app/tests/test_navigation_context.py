from its_multi_agent.backend.app.tests.test_stream_retry_state import FailingModel
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from its_multi_agent.backend.app.services.navigation_context import resolve_navigation_context
from its_multi_agent.backend.app.multi_agent.agent_factory import normalize_service_task
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext


def message(role, content):
    return {"role": role, "content": content}


HISTORY = [
    message("user", "从我这里到淄博推荐一下路线"),
    message("assistant", "你从哪里出发？出行方式是驾车还是公共交通？淄博具体哪里？"),
    message("user", "都可以"),
    message("assistant", "请补充出发地、出行方式和目的地。"),
]


class NavigationContextTest(unittest.TestCase):
    def test_screenshot_short_answers_preserve_destination(self):
        state = resolve_navigation_context("郑州", HISTORY)
        self.assertEqual((state.origin, state.destination), ("郑州", "淄博"))
        self.assertTrue(state.flexible)

    def test_any_mode_does_not_invent_origin(self):
        state = resolve_navigation_context("都可以", HISTORY[:2])
        self.assertEqual(state.origin, "")
        self.assertEqual(state.destination, "淄博")

    def test_repeated_non_location_answer_preserves_pending_task(self):
        history = [*HISTORY[:1], message("assistant", "目的地是淄博。你从哪个城市或地点出发？"),
                   message("user", "都可以"), message("assistant", "你从哪个城市或地点出发？")]
        state = resolve_navigation_context("郑州", history)
        self.assertEqual((state.origin, state.destination), ("郑州", "淄博"))

    def test_wrong_assistant_question_cannot_replace_user_destination(self):
        state = resolve_navigation_context("郑州", [*HISTORY, message("assistant", "你想到郑州的哪里？出发地是哪里？")])
        self.assertEqual((state.origin, state.destination), ("郑州", "淄博"))

    def test_correction_and_new_route(self):
        history = [*HISTORY, message("user", "郑州"), message("assistant", "从郑州到淄博。")]
        changed = resolve_navigation_context("改去济南", history)
        self.assertEqual((changed.origin, changed.destination), ("郑州", "济南"))
        new = resolve_navigation_context("从北京到上海怎么走", history)
        self.assertEqual((new.origin, new.destination), ("北京", "上海"))
        self.assertFalse(new.flexible)

    def test_new_topic_cancel_and_empty_session_do_not_inherit(self):
        for text in ("解释一下递归", "郑州天气", "不用了", "你好", "你是什么模型"):
            self.assertIsNone(resolve_navigation_context(text, HISTORY))
        self.assertIsNone(resolve_navigation_context("郑州", []))
        self.assertIsNone(resolve_navigation_context("郑州", [*HISTORY, message("user", "解释递归"), message("assistant", "递归是……")]))

    def test_no_placeholder_location_and_combined_task_not_intercepted(self):
        self.assertIsNone(resolve_navigation_context("我这里", HISTORY))
        self.assertIsNone(resolve_navigation_context("查知识库故障原因并规划去淄博的路线", []))

    def test_child_gets_restored_slots_even_when_main_reverses_them(self):
        state = resolve_navigation_context("郑州", HISTORY)
        result = json.loads(normalize_service_task(json.dumps({
            "request": "去郑州", "origin_hint": "淄博", "destination_hint": "郑州",
        }), state.task()))
        self.assertEqual((result["origin_hint"], result["destination_hint"]), ("郑州", "淄博"))
        self.assertTrue(result["needs_navigation"])
        self.assertIn("不限", result["request"])
        self.assertEqual(json.loads(normalize_service_task("", state.task()))["destination_hint"], "淄博")


class NavigationChatTest(unittest.IsolatedAsyncioTestCase):
    async def run_chat(self, query, history, plugins=None):
        target = "its_multi_agent.backend.app.services.agent_service."
        if plugins is None:
            plugins = ["map"]
        archived = [*history, message("user", query)]
        result = SimpleNamespace(final_output="从郑州到淄博，可以比较驾车和公共交通。", cancel=lambda: None)

        async def stream(*args, **kwargs):
            return
            yield

        with (
            patch(target + "memory_service.extract_and_store", AsyncMock()),
            patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
            patch(target + "session_service.prepare_history", return_value=archived),
            patch(target + "session_service.save_history") as save,
            patch(target + "attachment_service.prepare_history", side_effect=lambda _u, h, **kw: list(h)),
            patch(target + "resolve_profile", return_value=SimpleNamespace(supports_tools=True, model_name="offline-test")),
            patch(target + "model_for", return_value=FailingModel()),
            patch(target + "build_orchestrator_agent", return_value=object()) as build,
            patch(target + "Runner.run_streamed", return_value=result) as generate,
            patch(target + "process_stream_response", stream),
            patch(target + "asyncio.create_task", side_effect=lambda coro: coro.close()),
        ):
            packets = [json.loads(packet.removeprefix("data: ")) async for packet in MultiAgentService.process_task(
                ChatMessageRequest(query=query, context=UserContext(session_id="s"), enabled_plugins=plugins, confirmed_plugins=["map"] if "map" in plugins else []),
                user_id="alice", flag=False,
            )]
        return packets, save, build, generate

    async def test_followup_reaches_main_and_child_context_without_rewriting_archive(self):
        packets, save, build, generate = await self.run_chat("郑州", HISTORY)
        self.assertEqual(packets[-1]["metadata"]["finishReason"], "NORMAL")
        task = generate.call_args.kwargs["context"].navigation_task
        self.assertEqual((task.origin_hint, task.destination_hint), ("郑州", "淄博"))
        self.assertIn("query_service_station_and_navigate", build.call_args.kwargs["enabled_tools"])
        self.assertIn("current_navigation_task", json.dumps(generate.call_args.kwargs["input"]))
        stored = save.call_args.args[2]
        self.assertEqual(stored[-2]["content"], "郑州")
        self.assertNotIn("current_navigation_task", json.dumps(stored))

    async def test_clarification_only_asks_missing_origin(self):
        packets, save, build, generate = await self.run_chat("都可以", HISTORY[:2])
        generate.assert_not_called()
        reply = save.call_args.args[2][-1]["content"]
        self.assertIn("淄博", reply)
        self.assertIn("出发", reply)
        self.assertNotIn("出行方式", reply)

    async def test_disabled_map_stays_disabled(self):
        packets, save, build, generate = await self.run_chat("郑州", HISTORY, plugins=[])
        generate.assert_not_called()
        self.assertIn("未启用", save.call_args.args[2][-1]["content"])


if __name__ == "__main__":
    unittest.main()
