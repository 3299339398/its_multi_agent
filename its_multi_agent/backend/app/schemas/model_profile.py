from typing import Literal, Optional

from pydantic import BaseModel, Field


ModelRole = Literal["reasoning", "chat", "vision"]


class ModelProfileCreate(BaseModel):
    """用户提交的模型配置字段，配置标识由服务端分配。"""
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="openai-compatible", min_length=1, max_length=64)
    model_name: str = Field(min_length=1, max_length=256)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=1024)
    roles: tuple[ModelRole, ...] = ("chat",)
    supports_tools: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_streaming: bool = True
    context_window_tokens: Optional[int] = Field(default=None, ge=1024, le=2000000)
    max_output_tokens: Optional[int] = Field(default=None, ge=256, le=1000000)


class ModelProfile(ModelProfileCreate):
    """服务端模型配置，API 密钥不会离开后端。"""

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class ModelProfilePublic(BaseModel):
    id: str
    name: str
    provider: str
    model_name: str
    roles: tuple[ModelRole, ...]
    supports_tools: bool
    supports_vision: bool
    supports_reasoning: bool
    supports_streaming: bool
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
