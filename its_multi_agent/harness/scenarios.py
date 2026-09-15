import json
from pathlib import Path
from typing import Any

from .models import Scenario


def load_scenarios(path: str | Path) -> list[Scenario]:
    """Load and validate scenario definitions from a JSON file."""
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("scenario file must contain a JSON array")
    scenarios = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id") or not item.get("input"):
            raise ValueError("each scenario requires non-empty id and input")
        scenarios.append(
            Scenario(
                id=str(item["id"]),
                input=str(item["input"]),
                user_context=item.get("user_context", {}),
                expected_agents=tuple(item.get("expected_agents", ())),
                expected_tools=tuple(item.get("expected_tools", ())),
                must_include=tuple(item.get("must_include", ())),
                forbidden_tools=tuple(item.get("forbidden_tools", ())),
                expected_tool_order=tuple(item.get("expected_tool_order", ())),
                expected_source_origins=tuple(item.get("expected_source_origins", ())),
            )
        )
    return scenarios
