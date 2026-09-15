from .models import AgentRunResult, Scenario, ScenarioResult


def grade_result(scenario: Scenario, result: AgentRunResult) -> ScenarioResult:
    """Apply deterministic, explainable checks to one agent run."""
    expectations = (*scenario.expected_tools, *scenario.expected_agents, *scenario.must_include,
                    *scenario.forbidden_tools, *scenario.expected_tool_order, *scenario.expected_source_origins)
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
        "expected_agents": all(agent in result.agent_transitions for agent in scenario.expected_agents),
        "required_content": isinstance(result.final_answer, str) and all(
            isinstance(text, str) and text.casefold() in result.final_answer.casefold()
            for text in scenario.must_include
        ),
    }
    return ScenarioResult(
        scenario_id=scenario.id,
        passed=all(checks.values()),
        checks=checks,
        error=result.error,
    )
