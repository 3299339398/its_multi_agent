"""Agent 工具输入和运行时策略契约。"""

from dataclasses import dataclass
from typing import Literal

from math import isfinite

from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True)
class ToolPolicyDecision:
    """一次工具调用的统一策略判定，不包含用户输入或工具返回内容。"""

    tool_name: str
    allowed: bool
    confirmed: bool
    risk_level: Literal["low", "medium", "high"]
    side_effect_level: Literal["read", "external", "write"]
    reason: str

    @property
    def permitted(self) -> bool:
        return self.allowed and self.confirmed


class KnowledgeToolRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    knowledge_space: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[\w.-]+$")
    domain: str = Field(default="general", min_length=1, max_length=64, pattern=r"^[\w.-]+$")


class WebSearchToolRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)


class LocationToolRequest(BaseModel):
    user_input: str = Field(default="", max_length=500)


class RepairShopToolRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    limit: int = Field(default=3, ge=1, le=10)
    brand: str = Field(default="", max_length=128)
    repair_type: str = Field(default="", max_length=128)

    @field_validator("lat", "lng")
    @classmethod
    def finite_coordinate(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("坐标必须是有限数字")
        return value
