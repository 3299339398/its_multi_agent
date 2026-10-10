"""使用 LangGraph 编排单次请求中的复杂任务。"""
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
    """为一次 PlanExecutor 请求创建独立的任务图。

    节点复用已有的模型服务调用方法，由 LangGraph 管理状态转换，
    SSE 状态快照仍由 PlanExecutor 发送。
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
        async for _snapshot in executor.execute_plan(
            state["plan"], state["goal"], state["history"],
            state.get("has_attachments", False), state.get("attachment_sources") or [],
        ):
            pass
        return state

    graph.add_node("planner", plan_node)
    graph.add_node("executor", execute_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor" if execute else END)
    if not execute:
        return graph.compile()
    graph.add_edge("executor", END)
    return graph.compile()
