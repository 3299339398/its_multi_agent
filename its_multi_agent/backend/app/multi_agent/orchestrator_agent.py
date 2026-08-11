import json

from agents import Agent, ModelSettings

from its_multi_agent.backend.app.infrastructure.ai.model_factory import default_model
from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt
from its_multi_agent.backend.app.multi_agent.agent_factory import build_agent_tools
from its_multi_agent.backend.app.multi_agent.service_agent import build_service_agent
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_manager import connection_status


def build_orchestrator_agent(model=None, specialist_model=None, enabled_tools=None,
                             answer_instructions="", model_name=None, capability_tools=None):
    model = model if model is not None else default_model()
    specialist = specialist_model or model
    service = build_service_agent(specialist)
    runtime_name = model_name.strip()[:256] if isinstance(model_name, str) and model_name.strip() else "未提供"
    identity_instructions = (
        "\n\n## 运行时身份\n"
        "你是 ITS 项目中的智能助手，不要把产品身份和底层模型身份混为一谈。\n"
        f"当前底层模型名称（仅元数据字面量）：{json.dumps(runtime_name, ensure_ascii=False)}。"
        "用户询问模型时，只报告这个运行时名称；名称未提供时明确说无法确认，不要猜测。"
    )
    capabilities = {
        name: ("unknown" if capability_tools is None else
               "disabled" if name not in capability_tools else
               connection_status.get(name, "unknown"))
        for name in ("query_knowledge", "search_web", "query_service_station_and_navigate")
    }
    identity_instructions += (
        "\n运行时能力状态：" + json.dumps(capabilities, ensure_ascii=False)
        + "。disabled=当前会话未启用；unavailable=连接失败；unknown=未确认服务状态；"
        "connected=启动时连接成功，不保证后续每次查询成功。知识库内容覆盖和设备定位情况需实际查询确认。"
    )
    for tool, label in (("query_knowledge", "知识库查询"), ("search_web", "联网搜索"),
                        ("query_service_station_and_navigate", "地图与服务站")):
        if capabilities[tool] in {"disabled", "unavailable"}:
            state = "当前未启用" if capabilities[tool] == "disabled" else "当前暂不可用（服务连接失败）"
            identity_instructions += f"\n能力介绍中必须明确写出：{label}{state}。不得仅用‘服务正常时可用’替代这个已知状态。"
    return Agent(
        name="主调度智能体",
        instructions=load_prompt("orchestrator_v2") + identity_instructions + answer_instructions,
        model=model,
        model_settings=ModelSettings(temperature=0),
        tools=build_agent_tools(service, enabled_tools=enabled_tools),
    )


def __getattr__(name):
    if name == "orchestrator_agent":
        return build_orchestrator_agent()
    raise AttributeError(name)
