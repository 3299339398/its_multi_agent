from .models import AgentRunResult, Scenario, ScenarioResult


def grade_result(scenario: Scenario, result: AgentRunResult) -> ScenarioResult:
    """对一次 Agent 运行执行确定且可解释的检查。"""
    expectations = (*scenario.expected_tools, *scenario.expected_agents, *scenario.must_include,
                    *scenario.forbidden_tools, *scenario.expected_tool_order, *scenario.expected_source_origins,
                    *scenario.expected_grounding_origins, *scenario.expected_plan_executors)
    calls = iter(result.tool_calls)
    ordered = all(any(actual == expected for actual in calls) for expected in scenario.expected_tool_order)
    checks = {
        "no_error": result.error is None,
        "nonempty_answer": isinstance(result.final_answer, str) and bool(result.final_answer.strip()),
        "meaningful_expectations": bool(expectations) and all(
            isinstance(item, str) and bool(item.strip()) for item in expectations
        ),
        "expected_tools": all(tool in result.tool_calls for tool in scenario.expected_tools),
        "forbidden_tools": not any(tool in result.tool_calls for tool in scenario.forbidden_tools),
        "tool_order": ordered,
        "expected_source_origins": all(
            any(source.get("origin") == origin for source in result.sources)
            for origin in scenario.expected_source_origins
        ),
        "expected_grounding_origins": all(
            any(trace.get("origin") == origin for trace in result.grounding_trace)
            for origin in scenario.expected_grounding_origins
        ),
        "expected_agents": all(agent in result.agent_transitions for agent in scenario.expected_agents),
        "expected_plan_executors": all(
            executor in result.plan_executors for executor in scenario.expected_plan_executors
        ),
        "required_content": isinstance(result.final_answer, str) and all(
            isinstance(text, str) and text.casefold() in result.final_answer.casefold()
            for text in scenario.must_include
        ),
        "expected_route": scenario.expected_route is None or result.route == scenario.expected_route,
        "latency_budget": scenario.max_latency_ms is None or result.latency_ms <= scenario.max_latency_ms,
    }
    if result.duplicate_side_effects is not None:
        checks["no_duplicate_side_effects"] = result.duplicate_side_effects == 0
    return ScenarioResult(
        scenario_id=scenario.id,
        passed=all(checks.values()),
        checks=checks,
        error=result.error,
        latency_ms=result.latency_ms,
        route=result.route,
    )
