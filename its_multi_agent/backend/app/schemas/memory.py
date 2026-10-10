"""长期记忆的模型输出契约。

记忆内容来自用户文字和模型提取结果，必须先通过这个小契约，才能进入
向量库或后续上下文。它不是数据库模型，也不执行记忆中的任何文本。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    content: StrictStr = Field(min_length=2, max_length=500)
    memory_type: Literal["profile", "device", "preference", "troubleshooting_state", "fact"] = "fact"
    importance: float = Field(default=0.5, ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("content")
    @classmethod
    def reject_control_text(cls, value: str) -> str:
        lowered = "".join(value.casefold().split())
        blocked = (
            "忽略系统", "忽略之前", "系统提示", "系统规则", "开发者消息", "越过权限", "越权",
            "密钥", "密码", "访问令牌", "api key", "api_key", "api-key", "access token", "password", "secret",
            "调用工具", "执行命令", "修改文件", "不要遵守", "system prompt", "developer message",
            "ignore previous", "ignore all", "ignore system", "ignore the previous",
        )
        if any("".join(marker.casefold().split()) in lowered for marker in blocked):
            raise ValueError("memory content contains control text")
        return value
