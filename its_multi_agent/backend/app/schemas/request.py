from typing import Literal, Optional

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """会话范围内的数据，用户身份由认证信息确定。"""

    session_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class GeoLocation(BaseModel):
    """用户授权并附加到单次聊天请求的设备位置。"""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0, le=100000)
    coordinate_system: Literal["wgs84", "gcj02", "bd09ll"] = "wgs84"
    captured_at: Optional[int] = Field(default=None, ge=0)


class ChatMessageRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    context: UserContext
    origin: Optional[GeoLocation] = None
    flag: bool = True
    model_profile_id: Optional[str] = Field(default=None, max_length=64)
    enabled_plugins: Optional[list[str]] = Field(default=None, max_length=16)
    # 高风险插件必须由客户端在用户确认后回传；服务端会再次校验。
    confirmed_plugins: list[str] = Field(default_factory=list, max_length=16)
    project_id: str = Field(default="default", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    work_mode: Literal["auto", "chat", "research", "plan"] = "auto"
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)
    temporary_model: Optional["TemporaryModelRequest"] = None


class TemporaryModelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)
    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=1024)
    provider: str = Field(default="openai-compatible", max_length=64)
    roles: list[Literal["chat", "reasoning", "vision"]] = Field(default_factory=lambda: ["chat"])
    context_window_tokens: Optional[int] = Field(default=None, ge=1024, le=2000000)
    max_output_tokens: Optional[int] = Field(default=None, ge=256, le=1000000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=8, max_length=256)


class RegisterRequest(LoginRequest):
    """公开客户端注册请求，用户角色始终由服务端分配。"""


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    plugins: list[str] = Field(default_factory=list, max_length=16)


class KnowledgeQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    knowledge_space: str = Field(
        default="default", min_length=1, max_length=64,
        pattern=r"^[\w.-]+$",
    )
    domain: str = Field(
        default="general", min_length=1, max_length=64,
        pattern=r"^[\w.-]+$",
    )
