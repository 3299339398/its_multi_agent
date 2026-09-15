"""Planning specialist using the same provider and validated JSON contract."""
from its_multi_agent.backend.app.infrastructure.ai.prompt_loader import load_prompt
from its_multi_agent.backend.app.schemas.task_plan import TaskPlan
from its_multi_agent.backend.app.services.grounding_workflow import GroundingWorkflow


class PlanningAgent:
    name = "复杂任务规划专家"

    def __init__(self, model):
        self.workflow = GroundingWorkflow(model)

    async def plan(self, goal, history, tools):
        return await self.workflow._structured(load_prompt("planning_agent"), {
            "goal": goal, "history": history[-6:], "available_tools": sorted(tools),
        }, TaskPlan)
