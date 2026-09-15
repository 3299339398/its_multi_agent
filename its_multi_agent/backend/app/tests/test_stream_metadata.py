import json
import unittest
from types import SimpleNamespace

from agents import Agent
from agents.items import ToolCallItem
from openai.types.responses import ResponseFunctionToolCall

from its_multi_agent.backend.app.services.stream_response_service import process_stream_response


class StreamMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_and_agent_events_keep_raw_names_alongside_display_html(self):
        agent = Agent(name="Test expert")
        item = ToolCallItem(agent=agent, raw_item=ResponseFunctionToolCall(
            type="function_call", name="query_knowledge", arguments="{}", call_id="call-1",
        ))

        async def events():
            yield SimpleNamespace(type="agent_updated_stream_event", new_agent=agent)
            yield SimpleNamespace(type="run_item_stream_event", name="tool_called", item=item)

        packets = [json.loads(packet.removeprefix("data: ")) async for packet in
                   process_stream_response(SimpleNamespace(stream_events=events))]
        self.assertEqual(packets[0]["metadata"].get("agentName"), "Test expert")
        self.assertEqual(packets[1]["metadata"].get("toolName"), "query_knowledge")
        self.assertIn("tool-call", packets[1]["content"]["text"])
        self.assertEqual(packets[-1]["metadata"]["finishReason"], "NORMAL")
