from typing import Literal

from pydantic import BaseModel, Field


ModelRole = Literal["reasoning", "chat", "vision"]


class ModelProfileCreate(BaseModel):
    """User-supplied profile fields; identity is assigned by the server."""
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


class ModelProfile(ModelProfileCreate):
    """A server-side model profile. API keys never leave the backend."""

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
