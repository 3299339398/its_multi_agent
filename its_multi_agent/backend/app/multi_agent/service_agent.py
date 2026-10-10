from agents import Agent, ModelSettings, set_tracing_disabled

from its_multi_agent.backend.app.infrastructure.ai.model_factory import default_model
from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt
from its_multi_agent.backend.app.infrastructure.tools.local.service_station import (
    query_nearest_repair_shops_by_coords,
    resolve_user_location_from_text,
)
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_servers import (
    map_mcp_client_for,
)


set_tracing_disabled(True)


def build_service_agent(model=None, max_output_tokens=2048, context=None):
    return Agent(
        name="全能业务智能体",
        instructions=load_prompt("comprehensive_service_agent"),
        model=model if model is not None else default_model(),
        model_settings=ModelSettings(temperature=0, max_tokens=max_output_tokens),
        tools=[resolve_user_location_from_text, query_nearest_repair_shops_by_coords],
        # 未提供请求上下文时也使用空权限视图，避免直接暴露完整百度 MCP。
        mcp_servers=[map_mcp_client_for(context)],
    )
