from dataclasses import replace
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .grader import grade_result
from .metrics import summarize_runs
from .models import AgentRunResult, Scenario, ScenarioResult

Executor = Callable[[Scenario], AgentRunResult | Awaitable[AgentRunResult]]


async def run_scenario(executor: Executor, scenario: Scenario) -> ScenarioResult:
    """通过注入的执行器运行一个场景，并评估运行结果。"""
    started = time.perf_counter()
    try:
        value = executor(scenario)
        result = await value if inspect.isawaitable(value) else value
        if not isinstance(result, AgentRunResult):
            raise TypeError("executor must return AgentRunResult")
        if result.latency_ms <= 0:
            result = replace(result, latency_ms=(time.perf_counter() - started) * 1000)
    except Exception as exc:
        result = AgentRunResult(
            latency_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )
    return grade_result(scenario, result)


async def run_suite(executor: Executor, scenarios: list[Scenario]) -> dict:
    """运行一组场景并返回逐例结果和可比较的指标快照。"""
    pairs = []
    for scenario in scenarios:
        started = time.perf_counter()
        try:
            value = executor(scenario)
            run = await value if inspect.isawaitable(value) else value
            if not isinstance(run, AgentRunResult):
                raise TypeError("executor must return AgentRunResult")
        except Exception as exc:
            run = AgentRunResult(error=f"{type(exc).__name__}: {exc}", latency_ms=(time.perf_counter() - started) * 1000)
        if run.latency_ms <= 0:
            run = AgentRunResult(
                **{**run.__dict__, "latency_ms": (time.perf_counter() - started) * 1000}
            )
        graded = grade_result(scenario, run)
        pairs.append((scenario, run, graded))
    return {
        "metrics": summarize_runs(pairs),
        "results": [graded.__dict__ for _scenario, _run, graded in pairs],
    }
