import unittest
from types import SimpleNamespace

from agents import Agent, Model, Runner, RunConfig
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.responses import ResponseReasoningTextDeltaEvent, ResponseReasoningSummaryTextDeltaEvent

from its_multi_agent.backend.app.services import stream_response_service as stream


class FailingModel(Model):
    def __init__(self, answer=False):
        self.answer = answer

    async def get_response(self, *args, **kwargs):
        raise ConnectionError("temporary")

    async def stream_response(self, *args, **kwargs):
        if self.answer:
            yield ResponseTextDeltaEvent(type="response.output_text.delta", delta="partial", content_index=0,
                                         item_id="message", output_index=0, sequence_number=0, logprobs=[])
        raise ConnectionError("temporary")


class StreamRetryStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_reasoning_and_raw_tool_calls_prevent_retry(self):
        data_items = [
            ResponseReasoningTextDeltaEvent.model_construct(type="response.reasoning_text.delta", delta="thinking"),
            ResponseReasoningSummaryTextDeltaEvent.model_construct(type="response.reasoning_summary_text.delta", delta="summary"),
            SimpleNamespace(type="response.function_call_arguments.delta"),
        ]
        for data in data_items:
            with self.subTest(data=type(data).__name__):
                async def events():
                    yield SimpleNamespace(type="raw_response_event", data=data)
                    raise ConnectionError("temporary")
                state = stream.StreamResponseState()
                with self.assertRaises(ConnectionError):
                    async for _ in stream.process_stream_response(SimpleNamespace(stream_events=events), state=state):
                        pass
                self.assertFalse(state.retry_safe)

    async def test_real_sdk_initial_agent_event_allows_retry(self):
        state = stream.StreamResponseState()
        result = Runner.run_streamed(Agent(name="test", model=FailingModel()), "hello", run_config=RunConfig(tracing_disabled=True))
        packets = []
        try:
            with self.assertRaises(ConnectionError):
                async for packet in stream.process_stream_response(result, state=state):
                    packets.append(packet)
        finally:
            result.cancel()
        self.assertTrue(packets, "SDK must emit its initial agent update")
        self.assertTrue(state.retry_safe)

    async def test_real_sdk_answer_prevents_retry(self):
        state = stream.StreamResponseState()
        result = Runner.run_streamed(Agent(name="test", model=FailingModel(answer=True)), "hello", run_config=RunConfig(tracing_disabled=True))
        try:
            with self.assertRaises(ConnectionError):
                async for _ in stream.process_stream_response(result, state=state):
                    pass
        finally:
            result.cancel()
        self.assertFalse(state.retry_safe)

    async def test_tool_side_effect_without_answer_prevents_retry(self):
        async def events():
            yield SimpleNamespace(type="run_item_stream_event", name="tool_output", item=None)
            raise ConnectionError("temporary")
        state = stream.StreamResponseState()
        with self.assertRaises(ConnectionError):
            async for _ in stream.process_stream_response(SimpleNamespace(stream_events=events), state=state):
                pass
        self.assertTrue(state.tool_side_effects)
        self.assertFalse(state.retry_safe)
