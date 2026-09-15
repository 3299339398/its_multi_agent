"""Opt-in live model smoke check; stores no user history or credentials."""
import json
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from its_multi_agent.backend.app.api.routers import router
from its_multi_agent.backend.app.api.dependencies import get_current_user


def main():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "smoke", "username": "smoke", "role": "user"}
    goal = "分步执行两个独立步骤：先用一句话解释递归；再根据上一步的解释给一个不超过十行的 Python 递归示例。请将解释和示例分别验收。"
    target = "its_multi_agent.backend.app.services.agent_service."
    with (
        patch(target + "memory_service.extract_and_store", AsyncMock()),
        patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
        patch(target + "session_service.prepare_history", return_value=[{"role": "user", "content": goal}]),
        patch(target + "session_service.save_history"),
        TestClient(app) as client,
    ):
        response = client.post("/api/query", json={"query": goal, "context": {"session_id": "smoke"}, "enabled_plugins": []})
    packets = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    plans = [p["content"] for p in packets if p["content"]["contentType"] == "sagegpt/plan"]
    answer = "".join(p["content"].get("text", "") for p in packets if p["content"].get("kind") == "ANSWER")
    print(json.dumps({"http": response.status_code, "plan": plans[-1] if plans else None,
                      "answer": answer, "finish": packets[-1]["metadata"]["finishReason"]}, ensure_ascii=False))
    assert response.status_code == 200 and plans[-1]["status"] == "completed" and answer
    assert len(plans[-1]["steps"]) >= 2
    assert packets[-1]["metadata"]["finishReason"] == "NORMAL"


if __name__ == "__main__":
    main()
