"""LangGraph orchestration for request-scoped complex tasks."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class TaskGraphState(TypedDict, total=False):
    goal: str
    history: list[dict]
    has_attachments: bool
    attachment_sources: list[dict]
    plan: Any
    error: str


def build_task_graph(executor, *, execute: bool = True):
    """Build a fresh graph bound to one PlanExecutor request.

    Nodes call the existing provider-aware methods; LangGraph owns the state
    transition boundary, while SSE snapshots remain emitted by PlanExecutor.
    """
    graph = StateGraph(TaskGraphState)

    async def plan_node(state):
        try:
            plan = await executor.create_plan(state["goal"], state["history"])
            return {"plan": plan}
        except Exception:
            return {"error": "plan_failed"}

    async def execute_node(state):
        if state.get("error"):
            return state
        await executor.execute_plan(state["plan"], state["goal"], state["history"],
                                    state.get("has_attachments", False), state.get("attachment_sources") or [])
        return state

    graph.add_node("planner", plan_node)
    graph.add_node("executor", execute_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor" if execute else END)
    if not execute:
        return graph.compile()
    graph.add_edge("executor", END)
    return graph.compile()
