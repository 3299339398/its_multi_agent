from typing import Dict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from its_multi_agent.backend.app.services.auth_service import AuthConfigurationError, auth_service


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing authentication token")
    try:
        return auth_service.decode_token(credentials.credentials)
    except AuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except jwt.PyJWTError as error:
        raise _unauthorized("Invalid or expired authentication token") from error


def get_current_admin(
    user: Dict[str, str] = Depends(get_current_user),
) -> Dict[str, str]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return user


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
