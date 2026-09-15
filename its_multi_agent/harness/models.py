from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Scenario:
    id: str
    input: str
    user_context: Mapping[str, Any] = field(default_factory=dict)
    expected_agents: Sequence[str] = field(default_factory=tuple)
    expected_tools: Sequence[str] = field(default_factory=tuple)
    must_include: Sequence[str] = field(default_factory=tuple)
    forbidden_tools: Sequence[str] = field(default_factory=tuple)
    expected_tool_order: Sequence[str] = field(default_factory=tuple)
    expected_source_origins: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentRunResult:
    final_answer: str = ""
    tool_calls: Sequence[str] = field(default_factory=tuple)
    agent_transitions: Sequence[str] = field(default_factory=tuple)
    latency_ms: float = 0.0
    error: str | None = None
    sources: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    passed: bool
    checks: Mapping[str, bool]
    error: str | None = None
