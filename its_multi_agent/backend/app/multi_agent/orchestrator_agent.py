import json

from agents import Agent, ModelSettings

from its_multi_agent.backend.app.infrastructure.ai.model_factory import default_model
from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt
from its_multi_agent.backend.app.multi_agent.agent_factory import build_agent_tools
from its_multi_agent.backend.app.multi_agent.fork_runtime import ForkTemplate
from its_multi_agent.backend.app.multi_agent.service_agent import build_service_agent
from its_multi_agent.backend.app.infrastructure.tools.mcp.mcp_manager import connection_status


def runtime_instructions(model_name=None, capability_tools=None, answer_instructions=""):
    """生成本请求的动态规则；Fork 模式将其放到分支消息而非固定前缀。"""
    runtime_name = model_name.strip()[:256] if isinstance(model_name, str) and model_name.strip() else "未提供"
    identity = (
        "\n\n## 运行时身份\n"
        "你是知行项目中的智能助手，不要把产品身份和底层模型身份混为一谈。\n"
        f"当前底层模型名称（仅元数据字面量）：{json.dumps(runtime_name, ensure_ascii=False)}。"
        "用户询问模型时，只报告这个运行时名称；名称未提供时明确说无法确认，不要猜测。"
    )
    capabilities = {
        name: ("unknown" if capability_tools is None else
               "disabled" if name not in capability_tools else
               connection_status.get(name, "connected" if name == "replace_code" else "unknown"))
        for name in ("query_knowledge", "search_web", "query_service_station_and_navigate", "create_file", "replace_code")
    }
    identity += (
        "\n运行时能力状态：" + json.dumps(capabilities, ensure_ascii=False)
        + "。disabled=当前会话未启用；unavailable=连接失败；unknown=未确认服务状态；"
        "connected=启动时连接成功，不保证后续每次查询成功。知识库内容覆盖和设备定位情况需实际查询确认。"
    )
    for tool, label in (("query_knowledge", "知识库查询"), ("search_web", "联网搜索"),
                        ("query_service_station_and_navigate", "地图与服务站"),
                        ("create_file", "文件输出"),
                        ("replace_code", "工程修改")):
        if capabilities[tool] in {"disabled", "unavailable"}:
            state = "当前未启用" if capabilities[tool] == "disabled" else "当前暂不可用（服务连接失败）"
            identity += f"\n能力介绍中必须明确写出：{label}{state}。不得仅用‘服务正常时可用’替代这个已知状态。"
    identity += (
        "\n工具定义存在不代表当前请求已授权。disabled 工具不得调用。"
        "用户要求生成可下载文件而 create_file 未启用时，说明需要启用文件输出并确认授权，"
        "可以直接提供代码，但不得声称文件已经生成。"
        "工具返回未启用、未获确认或权限拒绝时停止尝试该工具，提示用户补充授权，不能反复调用。"
    )
    return identity + answer_instructions


def build_orchestrator_agent(model=None, specialist_model=None, enabled_tools=None,
                             answer_instructions="", model_name=None, capability_tools=None,
                             max_output_tokens=None, fork_template: ForkTemplate | None = None):
    model = model if model is not None else default_model()
    specialist = specialist_model or model
    service = build_service_agent(
        specialist, max_output_tokens=min(max_output_tokens or 2048, 2048),
    )
    if fork_template is not None:
        return fork_template.build_agent()
    identity_instructions = runtime_instructions(model_name, capability_tools, answer_instructions)
    return Agent(
        name="主调度智能体",
        instructions=load_prompt("orchestrator_v2") + identity_instructions,
        model=model,
        model_settings=ModelSettings(temperature=0, max_tokens=max_output_tokens),
        tools=build_agent_tools(service, enabled_tools=enabled_tools),
    )


def __getattr__(name):
    if name == "orchestrator_agent":
        return build_orchestrator_agent()
    raise AttributeError(name)
