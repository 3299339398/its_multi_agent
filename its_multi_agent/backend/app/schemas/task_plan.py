"""Bounded plans; executors are application capabilities, never arbitrary code."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^step-[1-6]$")
    title: str = Field(min_length=1, max_length=100)
    executor: Literal["research", "technical", "service"]
    task: str = Field(min_length=1, max_length=5000)
    depends_on: list[str] = Field(default_factory=list, max_length=5)
    success_criteria: str = Field(min_length=1, max_length=500)


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def ordered_dependencies(self):
        seen = set()
        for step in self.steps:
            if step.id in seen or not set(step.depends_on).issubset(seen):
                raise ValueError("Steps must have unique IDs and depend only on earlier steps")
            seen.add(step.id)
        return self


class StepReview(BaseModel):
    complete: bool
    missing: str = Field(default="", max_length=500)
