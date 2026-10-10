import json
from pathlib import Path
from typing import Any

from .models import Scenario


_SCENARIO_FIELDS = {
    "id", "input", "user_context", "expected_route", "max_latency_ms", "expected_agents", "expected_tools",
    "must_include", "forbidden_tools", "expected_tool_order",
    "expected_source_origins", "expected_grounding_origins", "expected_plan_executors",
}
_CONTEXT_FIELDS = {
    "user_id", "session_id", "origin", "flag", "model_profile_id",
    "enabled_plugins", "confirmed_plugins", "project_id", "work_mode",
    "attachment_ids", "temporary_model",
}
_EXPECTATION_FIELDS = (
    "expected_agents", "expected_tools", "must_include", "forbidden_tools",
    "expected_tool_order", "expected_source_origins", "expected_grounding_origins",
    "expected_plan_executors",
)


def _string_sequence(item: dict, field: str) -> tuple[str, ...]:
    value = item.get(field, [])
    if not isinstance(value, list) or any(not isinstance(entry, str) or not entry.strip() for entry in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def load_scenarios(path: str | Path) -> list[Scenario]:
    """从 JSON 文件加载并校验场景定义。"""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("scenario file must contain a JSON array")
    scenarios = []
    seen_ids = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip() \
                or not isinstance(item.get("input"), str) or not item["input"].strip():
            raise ValueError("each scenario requires non-empty id and input")
        scenario_id = item["id"].strip()
        unknown = set(item).difference(_SCENARIO_FIELDS)
        if unknown:
            raise ValueError(f"unknown scenario fields: {sorted(unknown)}")
        if scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)
        user_context = item.get("user_context", {})
        if not isinstance(user_context, dict):
            raise ValueError("user_context must be an object")
        unknown_context = set(user_context).difference(_CONTEXT_FIELDS)
        if unknown_context:
            raise ValueError(f"unknown user_context fields: {sorted(unknown_context)}")
        expectations = {field: _string_sequence(item, field) for field in _EXPECTATION_FIELDS}
        if set(expectations["expected_tools"]).intersection(expectations["forbidden_tools"]):
            raise ValueError("expected_tools and forbidden_tools must not overlap")
        route, latency = item.get("expected_route"), item.get("max_latency_ms")
        if route is not None and (not isinstance(route, str) or not route.strip()):
            raise ValueError("expected_route must be a non-empty string")
        if latency is not None and (isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency <= 0):
            raise ValueError("max_latency_ms must be positive")
        scenarios.append(
            Scenario(
                id=scenario_id,
                input=item["input"].strip(),
                user_context=user_context,
                expected_route=route, max_latency_ms=latency,
                **expectations,
            )
        )
    return scenarios
