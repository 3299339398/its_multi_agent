from dataclasses import dataclass

from its_multi_agent.backend.app.schemas.request import GeoLocation
from its_multi_agent.backend.app.schemas.service_agent import ServiceTask


@dataclass(frozen=True)
class AgentRequestContext:
    """Request-scoped dependencies available to tools but hidden from the LLM."""

    user_id: str
    session_id: str
    origin: GeoLocation | None = None
    navigation_task: ServiceTask | None = None
    run_id: str | None = None
