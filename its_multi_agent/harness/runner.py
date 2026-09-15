import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .grader import grade_result
from .models import AgentRunResult, Scenario, ScenarioResult

Executor = Callable[[Scenario], AgentRunResult | Awaitable[AgentRunResult]]


async def run_scenario(executor: Executor, scenario: Scenario) -> ScenarioResult:
    """Run one scenario through an injected executor and grade its result."""
    started = time.perf_counter()
    try:
        value = executor(scenario)
        result = await value if inspect.isawaitable(value) else value
        if not isinstance(result, AgentRunResult):
            raise TypeError("executor must return AgentRunResult")
        if result.latency_ms <= 0:
            result = AgentRunResult(
                final_answer=result.final_answer,
                tool_calls=result.tool_calls,
                agent_transitions=result.agent_transitions,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=result.error,
                sources=result.sources,
            )
    except Exception as exc:
        result = AgentRunResult(
            latency_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )
    return grade_result(scenario, result)
