import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents import Agent
from agents.items import ToolCallItem
from openai.types.responses import ResponseFunctionToolCall

from its_multi_agent.backend.app.services.agent_hooks import AgentHookManager, AgentPolicyDenied
from its_multi_agent.backend.app.services.stream_response_service import process_stream_response


class AgentHookManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_register_emit_unregister_and_isolate_failures(self):
        manager = AgentHookManager()
        calls = []

        def failing(_payload):
            raise RuntimeError("telemetry is optional")

        async def recording(payload):
            calls.append(payload["value"])

        manager.register("before_run", failing)
        manager.register("before_run", recording)
        await manager.emit("before_run", {"value": 3})
        self.assertEqual(calls, [3])
        self.assertTrue(manager.unregister("before_run", recording))
        self.assertFalse(manager.unregister("before_run", recording))

    async def test_stream_events_emit_tool_and_agent_hooks(self):
        agent = Agent(name="Test expert")
        item = ToolCallItem(agent=agent, raw_item=ResponseFunctionToolCall(
            type="function_call", name="query_knowledge", arguments="{}", call_id="call-1",
        ))

        async def events():
            yield SimpleNamespace(type="agent_updated_stream_event", new_agent=agent)
            yield SimpleNamespace(type="run_item_stream_event", name="tool_called", item=item)
            yield SimpleNamespace(type="run_item_stream_event", name="tool_output", item=item)

        with patch(
            "its_multi_agent.backend.app.services.stream_response_service.agent_hooks.emit",
            new_callable=AsyncMock,
        ) as emit:
            [packet async for packet in process_stream_response(SimpleNamespace(stream_events=events))]
        self.assertEqual([call.args[0] for call in emit.await_args_list], [
            "agent_transition", "tool_call", "tool_output",
        ])

    async def test_policy_hook_can_deny_tool_execution(self):
        manager = AgentHookManager()
        manager.register("before_tool_call", lambda payload: {
            "allow": payload["tool_name"] != "create_file", "reason": "文件输出未获批准",
        })
        with self.assertRaisesRegex(AgentPolicyDenied, "文件输出"):
            await manager.authorize_tool({"tool_name": "create_file"})
        await manager.authorize_tool({"tool_name": "search_web"})


if __name__ == "__main__":
    unittest.main()
