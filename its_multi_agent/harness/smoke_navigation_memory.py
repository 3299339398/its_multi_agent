"""Opt-in real-model/SSE check, with isolated history and a stub map specialist."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from its_multi_agent.backend.app.api.routers import router
from its_multi_agent.backend.app.api.dependencies import get_current_user
from its_multi_agent.backend.app.tests.test_navigation_context import HISTORY, message


def main():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "smoke", "username": "smoke", "role": "user"}
    target = "its_multi_agent.backend.app.services.agent_service."
    tasks = []

    async def specialist(*args, **kwargs):
        task = json.loads(kwargs["input"])
        tasks.append(task)
        return SimpleNamespace(final_output=json.dumps({
            "status": "needs_user_input", "summary": "已确认从郑州到淄博，出行方式不限。",
            "missing_information": "精确地图导航需要郑州的具体出发地点；可以先提供城市间出行方式建议。",
        }, ensure_ascii=False))

    with (
        patch(target + "memory_service.extract_and_store", AsyncMock()),
        patch(target + "memory_service.retrieve", AsyncMock(return_value="")),
        patch(target + "session_service.prepare_history", return_value=[*HISTORY, message("user", "郑州")]),
        patch(target + "session_service.save_history"),
        patch("its_multi_agent.backend.app.multi_agent.agent_factory.Runner.run", side_effect=specialist),
        TestClient(app) as client,
    ):
        response = client.post("/api/query", json={"query": "郑州", "context": {"session_id": "smoke"}})
    packets = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    answer = "".join(p["content"].get("text", "") for p in packets if p["content"].get("kind") == "ANSWER")
    print(json.dumps({"http": response.status_code, "specialist_tasks": tasks, "answer": answer,
                      "finish": packets[-1]["metadata"]["finishReason"]}, ensure_ascii=False))
    assert response.status_code == 200 and answer
    assert packets[-1]["metadata"]["finishReason"] == "NORMAL"
    assert tasks and all(t["origin_hint"] == "郑州" and t["destination_hint"] == "淄博" for t in tasks)
    assert "郑州" in answer and "淄博" in answer


if __name__ == "__main__":
    main()
