"""Contracts exchanged between the orchestrator and the service specialist."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ServiceTask(BaseModel):
    """A bounded task handed from the main agent to the service specialist."""

    model_config = ConfigDict(extra="ignore")

    request: str = Field(min_length=1, max_length=5000)
    origin_hint: str = Field(default="", max_length=500)
    destination_hint: str = Field(default="", max_length=500)
    brand: str = Field(default="", max_length=128)
    repair_type: str = Field(default="", max_length=128)
    transport_mode: Literal["driving", "walking", "riding", "transit"] = "driving"
    needs_navigation: bool = False
    constraints: list[str] = Field(default_factory=list, max_length=8)


class ServiceAgentResult(BaseModel):
    """Machine-readable result returned by the service specialist."""

    model_config = ConfigDict(extra="ignore")

    status: Literal[
        "ok", "needs_user_input", "not_found", "unavailable", "invalid_request"
    ]
    summary: str = Field(default="", max_length=6000)
    missing_information: str = Field(default="", max_length=500)
    error: str = Field(default="", max_length=500)
    origin: dict[str, Any] | None = None
    destination: dict[str, Any] | None = None
    stations: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    route: dict[str, Any] | None = None
    navigation_url: str = Field(default="", max_length=2000)
