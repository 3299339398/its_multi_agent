from dataclasses import dataclass

from its_multi_agent.backend.app.schemas.request import GeoLocation
from its_multi_agent.backend.app.schemas.service_agent import ServiceTask


@dataclass(frozen=True)
class AgentRequestContext:
    """请求范围内供工具使用、但不向大模型暴露的依赖。"""

    user_id: str
    session_id: str
    origin: GeoLocation | None = None
    navigation_task: ServiceTask | None = None
    run_id: str | None = None
    code_workspace_root: str | None = None
    # 工具白名单必须由请求或分支明确提供；空集合表示本分支没有工具权限。
    allowed_tools: frozenset[str] = frozenset()
    # 仅在用户确认高风险插件后填充，由工具执行层再次检查。
    confirmed_tools: frozenset[str] = frozenset()
    project_id: str | None = None
