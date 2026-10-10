"""使用同一模型服务和结构化契约的任务规划专家。"""
from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt
from its_multi_agent.backend.app.schemas.task_plan import TaskPlan
from its_multi_agent.backend.app.services.grounding_workflow import GroundingWorkflow
from its_multi_agent.backend.app.services.context_budget import TokenLimits


class PlanningAgent:
    name = "复杂任务规划专家"

    def __init__(self, model, *, token_limits: TokenLimits | None = None,
                 model_name: str | None = None):
        self.workflow = GroundingWorkflow(model, token_limits=token_limits, model_name=model_name)

    async def plan(self, goal, history, tools):
        return await self.workflow._structured(load_prompt("planning_agent"), {
            "goal": goal, "history": history[-6:], "available_tools": sorted(tools),
        }, TaskPlan)
