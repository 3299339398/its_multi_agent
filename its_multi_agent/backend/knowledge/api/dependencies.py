import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from its_multi_agent.backend.knowledge.config.settings import settings


def verify_service_token(
    service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> None:
    expected = settings.KNOWLEDGE_SERVICE_TOKEN
    if not expected or len(expected) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service authentication is not configured",
        )
    if not service_token or not hmac.compare_digest(service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )
