"""Harness 运行的可量化指标。

指标只消费执行适配器返回的结构化结果，不把模型自报的正确率当作事实。
"""
from __future__ import annotations

from statistics import median
from typing import Iterable

from .models import AgentRunResult, Scenario, ScenarioResult


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return values[index]


def summarize_runs(
    pairs: Iterable[tuple[Scenario, AgentRunResult, ScenarioResult]],
) -> dict[str, float | int | dict[str, int]]:
    """输出路由、答案、引用、延迟和副作用指标。"""
    items = list(pairs)
    if not items:
        return {"sample_count": 0}
    results = [result for _scenario, _run, result in items]
    runs = [run for _scenario, run, _result in items]
    route_cases = [(scenario, run) for scenario, run, _result in items if scenario.expected_route]
    citation_cases = [run for scenario, run, _result in items if scenario.expected_source_origins]
    latencies = [run.latency_ms for run in runs if run.latency_ms > 0]
    first_events = [run.first_event_latency_ms for run in runs if run.first_event_latency_ms > 0]
    observed_effects = [run.duplicate_side_effects for run in runs if run.duplicate_side_effects is not None]
    return {
        "side_effect_observed_count": len(observed_effects),
        "sample_count": len(items),
        "scenario_pass_rate": sum(item.passed for item in results) / len(results),
        "no_error_rate": sum(run.error is None for run in runs) / len(runs),
        "nonempty_answer_rate": sum(bool(run.final_answer.strip()) for run in runs) / len(runs),
        "route_accuracy": (
            sum(run.route == scenario.expected_route for scenario, run in route_cases) / len(route_cases)
            if route_cases else None
        ),
        "source_origin_coverage": (
            sum(all(any(source.get("origin") == origin for source in run.sources)
                    for origin in scenario.expected_source_origins)
                for scenario, run in ((s, r) for s, r, _ in items if s.expected_source_origins))
            / len(citation_cases)
            if citation_cases else None
        ),
        "duplicate_side_effect_rate": sum(value > 0 for value in observed_effects) / len(observed_effects) if observed_effects else None,
        "median_latency_ms": median(latencies) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "median_first_event_latency_ms": median(first_events) if first_events else None,
        "p95_first_event_latency_ms": _percentile(first_events, 0.95),
        "finish_reasons": {
            "normal": sum(run.error is None for run in runs),
            "error": sum(run.error is not None for run in runs),
        },
    }
