import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import jwt

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.repositories.user_repository import UserRepository, user_repository


class AuthConfigurationError(RuntimeError):
    pass


class UserAlreadyExistsError(ValueError):
    pass


class AuthService:
    SCRYPT_N = 2**14
    SCRYPT_R = 8
    SCRYPT_P = 1
    HASH_LENGTH = 64
    ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    ALLOWED_ROLES = {"user", "admin"}

    def __init__(
        self,
        repository: UserRepository = user_repository,
        secret: Optional[str] = None,
        token_ttl_minutes: Optional[int] = None,
        bootstrap_users_json: Optional[str] = None,
    ) -> None:
        self._repository = repository
        self._secret = secret if secret is not None else settings.AUTH_JWT_SECRET
        self._token_ttl_minutes = token_ttl_minutes or settings.AUTH_TOKEN_TTL_MINUTES
        bootstrap = settings.AUTH_BOOTSTRAP_USERS_JSON if bootstrap_users_json is None else bootstrap_users_json
        self._bootstrap_users(bootstrap)

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, str]]:
        user = self._repository.get_by_username(username)
        if not user or not user["is_active"]:
            return None
        if not self.verify_password(password, user["password_hash"]):
            return None
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
        }

    def register(self, username: str, password: str) -> Dict[str, str]:
        """Register a client account. Public registration can never create admins."""
        username = username.strip()
        if not self.ID_PATTERN.fullmatch(username):
            raise ValueError("用户名只能包含字母、数字、下划线和短横线")
        if len(password) < 8:
            raise ValueError("密码长度不能少于 8 位")
        if self._repository.get_by_username(username):
            raise UserAlreadyExistsError("用户名已存在")
        if not self._repository.create_user(
            username, username, self.hash_password(password), role="user",
        ):
            raise UserAlreadyExistsError("用户名已存在")
        return {"user_id": username, "username": username, "role": "user"}

    def issue_token(self, user: Dict[str, str]) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "iat": now,
            "exp": now + timedelta(minutes=self._token_ttl_minutes),
            "iss": settings.AUTH_JWT_ISSUER,
        }
        return jwt.encode(payload, self._require_secret(), algorithm="HS256")

    def decode_token(self, token: str) -> Dict[str, str]:
        payload = jwt.decode(
            token,
            self._require_secret(),
            algorithms=["HS256"],
            issuer=settings.AUTH_JWT_ISSUER,
            options={"require": ["sub", "username", "role", "iat", "exp", "iss"]},
        )
        user_id = str(payload["sub"])
        user = self._repository.get_by_user_id(user_id)
        if (
            not user
            or not user["is_active"]
            or user["username"] != payload["username"]
            or user["role"] != payload["role"]
        ):
            raise jwt.InvalidTokenError("User is inactive or no longer exists")
        return {"user_id": user_id, "username": user["username"], "role": user["role"]}

    @classmethod
    def hash_password(cls, password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt,
            n=cls.SCRYPT_N, r=cls.SCRYPT_R, p=cls.SCRYPT_P,
            dklen=cls.HASH_LENGTH,
        )
        return "scrypt${}${}${}${}${}".format(
            cls.SCRYPT_N, cls.SCRYPT_R, cls.SCRYPT_P,
            cls._encode(salt), cls._encode(digest),
        )

    @classmethod
    def verify_password(cls, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded.split("$", 5)
            expected_bytes = cls._decode(expected)
            if algorithm != "scrypt":
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"), salt=cls._decode(salt),
                n=int(n), r=int(r), p=int(p), dklen=len(expected_bytes),
            )
            return hmac.compare_digest(actual, expected_bytes)
        except (TypeError, ValueError):
            return False

    def _bootstrap_users(self, raw_users: str) -> None:
        if not raw_users.strip():
            return
        try:
            users = json.loads(raw_users)
            if not isinstance(users, list):
                raise ValueError("AUTH_BOOTSTRAP_USERS_JSON must be a JSON array")
            for item in users:
                username = str(item["username"]).strip()
                password = str(item["password"])
                user_id = str(item.get("user_id") or username).strip()
                role = str(item.get("role", "user")).strip().lower()
                if not self.ID_PATTERN.fullmatch(username) or not self.ID_PATTERN.fullmatch(user_id):
                    raise ValueError("username and user_id may only contain letters, numbers, _ and -")
                if len(password) < 8:
                    raise ValueError("bootstrap passwords must contain at least 8 characters")
                if role not in self.ALLOWED_ROLES:
                    raise ValueError("bootstrap role must be 'user' or 'admin'")
                if password == "replace-with-a-strong-password":
                    raise ValueError("replace the bootstrap password placeholder before startup")
                existing_username = self._repository.get_by_username(username)
                existing_user_id = self._repository.get_by_user_id(user_id)
                if existing_username or existing_user_id:
                    if (
                        existing_username
                        and existing_user_id
                        and existing_username["user_id"] == user_id
                        and existing_user_id["username"] == username
                    ):
                        if existing_user_id["role"] != role:
                            self._repository.update_role(user_id, role)
                        continue
                    raise ValueError(f"bootstrap identity conflict for {username}/{user_id}")
                if self._repository.create_if_missing(
                    user_id, username, self.hash_password(password), role,
                ):
                    logger.info("Created bootstrap user %s", username)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AuthConfigurationError(f"Invalid AUTH_BOOTSTRAP_USERS_JSON: {error}") from error

    def _require_secret(self) -> str:
        if not self._secret or len(self._secret) < 32:
            raise AuthConfigurationError("AUTH_JWT_SECRET must contain at least 32 characters")
        return self._secret

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


auth_service = AuthService()
