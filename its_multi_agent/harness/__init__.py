"""面向 ITS Agent 的轻量、低依赖评测框架。"""

from .models import AgentRunResult, Scenario, ScenarioResult
from .runner import run_scenario
from .grader import grade_result
from .scenarios import load_scenarios
from .real_executor import execute_with_agents

__all__ = [
    "AgentRunResult",
    "Scenario",
    "ScenarioResult",
    "run_scenario",
    "grade_result",
    "load_scenarios",
    "execute_with_agents",
]
