from typing import Literal

from pydantic import BaseModel, Field


class FileArtifactCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=2_000_000)
    mime_type: Literal[
        "text/plain", "text/markdown", "application/json", "text/csv"
    ] = "text/plain"
    session_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    run_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class FileArtifactResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    session_id: str | None = None
    run_id: str | None = None
    created_at: int
    expires_at: int
    download_url: str
