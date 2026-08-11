from collections.abc import AsyncGenerator
from dataclasses import dataclass
from agents.run import RunResultStreaming
from openai.types.responses.response_stream_event import (
    ResponseTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningSummaryTextDeltaEvent,
)
from agents.items import ToolCallItem

from its_multi_agent.backend.app.utils.response_util import ResponseFactory
from its_multi_agent.backend.app.utils.text_util import format_tool_call_html, format_agent_update_html
from its_multi_agent.backend.app.schemas.response import ContentKind
from its_multi_agent.backend.app.services.agent_hooks import agent_hooks


@dataclass
class StreamResponseState:
    semantic_output: bool = False
    tool_side_effects: bool = False

    @property
    def retry_safe(self) -> bool:
        return not (self.semantic_output or self.tool_side_effects)


async def process_stream_response(
    streaming_result: RunResultStreaming,
    include_finish: bool = True,
    state: StreamResponseState | None = None,
) -> AsyncGenerator:
    """
    处理Agent流式的事假
    Args:
        streaming_result:  流式结果对象（RunResultStreaming）
    Returns:

    """

    state = state if state is not None else StreamResponseState()
    async for event in streaming_result.stream_events():
        # ------------------------------------------------------------------
        # 1. 文本与推理生成事件 (Text & Reasoning)
        # ------------------------------------------------------------------
        if event.type == "raw_response_event":
            data_type = getattr(event.data, "type", "")
            item_type = getattr(getattr(event.data, "item", None), "type", "")
            if "function_call" in data_type or item_type in {
                "function_call", "computer_call", "web_search_call", "file_search_call",
                "code_interpreter_call", "mcp_call", "local_shell_call", "shell_call",
            }:
                state.tool_side_effects = True
            # 1.1 常规文本输出 → ANSWER
            if isinstance(event.data, ResponseTextDeltaEvent):
                delta_text = event.data.delta
                if delta_text:
                    state.semantic_output = True
                yield "data: " + ResponseFactory.build_text(
                    delta_text, ContentKind.ANSWER
                ).model_dump_json() + "\n\n"

            # 1.2 推理过程输出 → THINKING  #  是OpenAI的推理模型（o1的推理过程被OpenAI封装到ResponseReasoningTextDeltaEvent对象中）
            elif ResponseReasoningTextDeltaEvent and isinstance(event.data, ResponseReasoningTextDeltaEvent):
                if event.data.delta:
                    state.semantic_output = True
                    yield "data: " + ResponseFactory.build_text(
                        event.data.delta, ContentKind.THINKING
                    ).model_dump_json() + "\n\n"

            # 1.3 推理摘要 → THINKING   # 非OpenAI的推理模型（Qwq的推理过程被OpenAI封装到ResponseReasoningSummaryTextDeltaEvent对象中）
            elif isinstance(event.data, ResponseReasoningSummaryTextDeltaEvent):
                if event.data.delta:
                    state.semantic_output = True
                    yield "data: " + ResponseFactory.build_text(
                        event.data.delta, ContentKind.THINKING
                    ).model_dump_json() + "\n\n"

        # ------------------------------------------------------------------
        # 2. 工具调用事件 (Tool Call)
        # ------------------------------------------------------------------
        elif event.type == "run_item_stream_event":
            if getattr(event, "name", "") in {"tool_called", "tool_output", "handoff_requested", "handoff_occured"}:
                state.tool_side_effects = True
                hook_event = "tool_call" if event.name in {"tool_called", "handoff_requested"} else "tool_output"
                item = getattr(event, "item", None)
                await agent_hooks.emit(hook_event, {
                    "event": event.name,
                    "tool_name": getattr(item, "raw_item", None) and getattr(item.raw_item, "name", None),
                    "agent_name": getattr(getattr(item, "agent", None), "name", None),
                })
            if hasattr(event, "name") and event.name == "tool_called":
                if isinstance(event.item, ToolCallItem) and event.item.type == "tool_call_item":
                    tool_name = event.item.raw_item.name

                    text = format_tool_call_html(tool_name)
                    # 构建 PROCESS 类型消息
                    yield "data: " + ResponseFactory.build_text(
                        text, ContentKind.PROCESS, tool_name=tool_name
                    ).model_dump_json() + "\n\n"

        # ------------------------------------------------------------------
        # 3. 智能体状态更新
        # ------------------------------------------------------------------
        elif event.type == "agent_updated_stream_event":
            await agent_hooks.emit("agent_transition", {
                "agent_name": getattr(getattr(event, "new_agent", None), "name", None),
            })
            new_agent_name = event.new_agent.name

            text = format_agent_update_html(new_agent_name)

            yield "data: " + ResponseFactory.build_text(
                text, ContentKind.PROCESS, agent_name=new_agent_name
            ).model_dump_json() + "\n\n"

        # ------------------------------------------------------------------
        # 4. 发送结束信号
        # ------------------------------------------------------------------
    if include_finish:
        yield "data: " + ResponseFactory.build_finish().model_dump_json() + "\n\n"
