import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.model_endpoint_policy import validate_model_base_url


class DuplicateModelProfileError(ValueError):
    pass


class ModelCredentialError(RuntimeError):
    pass


class UserModelProfileRepository:
    def __init__(self, db_path: Optional[str] = None):
        default = Path(__file__).resolve().parent.parent / "data" / "model_profiles.db"
        self.path = Path(db_path or getattr(settings, "MODEL_PROFILE_SQLITE_PATH", None) or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("CREATE TABLE IF NOT EXISTS model_profiles (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,provider TEXT NOT NULL,model_name TEXT NOT NULL,base_url TEXT NOT NULL,api_key TEXT NOT NULL,roles TEXT NOT NULL,created_at TEXT NOT NULL, UNIQUE(user_id,name))")
            columns = {row[1] for row in c.execute("PRAGMA table_info(model_profiles)")}
            if "capabilities" not in columns:
                c.execute("ALTER TABLE model_profiles ADD COLUMN capabilities TEXT")
            self._fernet = self._initialize_encryption(c)

    def _initialize_encryption(self, connection):
        key_path = Path(getattr(settings, "MODEL_PROFILE_ENCRYPTION_KEY_PATH", None) or str(self.path) + ".key")
        configured_key = getattr(settings, "MODEL_PROFILE_ENCRYPTION_KEY", None)
        key = configured_key.encode() if configured_key else key_path.read_bytes().strip() if key_path.exists() else None
        legacy_secret = getattr(settings, "MODEL_PROFILE_LEGACY_JWT_SECRET", None)
        if legacy_secret is None:
            legacy_secret = settings.AUTH_JWT_SECRET or ""
        legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256(legacy_secret.encode()).digest()))
        rows = connection.execute("SELECT id,api_key FROM model_profiles").fetchall()
        try:
            current = Fernet(key) if key is not None else None
        except (ValueError, TypeError):
            raise ModelCredentialError("Invalid model credentials encryption key; restore the original key") from None
        migrated = []
        for profile_id, ciphertext in rows:
            token = ciphertext.encode()
            if current is not None:
                try:
                    current.decrypt(token)
                    continue
                except InvalidToken:
                    pass
            try:
                migrated.append((profile_id, legacy.decrypt(token)))
            except InvalidToken:
                raise ModelCredentialError(
                    "Cannot decrypt stored model credentials; restore the original encryption key or set "
                    "MODEL_PROFILE_LEGACY_JWT_SECRET to the previous JWT secret before migration"
                ) from None
        # 在启用新的独立加密密钥前，先校验所有已有凭据。
        if current is None:
            current = Fernet(self._persist_key(key_path))
        for profile_id, plaintext in migrated:
            connection.execute("UPDATE model_profiles SET api_key=? WHERE id=?", (current.encrypt(plaintext).decode(), profile_id))
        return current

    @staticmethod
    def _persist_key(path: Path) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".model-key-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                if os.name == "nt":
                    identity = subprocess.run(
                        ["whoami"], check=True, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                    ).stdout.strip()
                    subprocess.run(["icacls", temporary, "/inheritance:r", "/grant:r", f"{identity}:F"],
                                   check=True, capture_output=True)
                handle.write(Fernet.generate_key())
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # 通过硬链接原子创建密钥文件，避免覆盖并发工作进程已创建的密钥。
                os.link(temporary, path)
            except FileExistsError:
                pass
            return path.read_bytes().strip()
        finally:
            os.unlink(temporary)

    @staticmethod
    def _capabilities(raw: str | None, roles: tuple) -> dict:
        capabilities = {
            "supports_tools": True, "supports_streaming": True,
            "supports_vision": "vision" in roles, "supports_reasoning": "reasoning" in roles,
            "context_window_tokens": None, "max_output_tokens": None,
        }
        if raw:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                capabilities.update(stored)
        return capabilities

    @contextmanager
    def _connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def list_public(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as c:
            rows = c.execute("SELECT id,name,provider,model_name,roles,capabilities FROM model_profiles WHERE user_id=? ORDER BY name", (user_id,)).fetchall()
        return [{"id": r[0], "name": r[1], "provider": r[2], "model_name": r[3], "roles": tuple(r[4].split(",")), **self._capabilities(r[5], tuple(r[4].split(",")))} for r in rows]

    def get(self, user_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as c:
            row = c.execute("SELECT id,name,provider,model_name,base_url,api_key,roles,capabilities FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id)).fetchone()
        if not row: return None
        return {"id": row[0], "name": row[1], "provider": row[2], "model_name": row[3], "base_url": row[4], "api_key": self._fernet.decrypt(row[5].encode()).decode(), "roles": tuple(row[6].split(",")), **self._capabilities(row[7], tuple(row[6].split(",")))}

    def save(self, user_id: str, data: Dict[str, Any]) -> str:
        base_url = validate_model_base_url(data["base_url"], settings)
        profile_id = "user-" + uuid.uuid4().hex
        roles = ",".join(data.get("roles") or ["chat"])
        capabilities = self._capabilities(None, tuple(roles.split(",")))
        capabilities.update({key: data[key] for key in capabilities if key in data})
        try:
            with self._connect() as c:
                c.execute("INSERT INTO model_profiles (id,user_id,name,provider,model_name,base_url,api_key,roles,created_at,capabilities) VALUES (?,?,?,?,?,?,?,?,datetime('now'),?)", (profile_id, user_id, data["name"], data.get("provider", "openai-compatible"), data["model_name"], base_url, self._fernet.encrypt(data["api_key"].encode()).decode(), roles, json.dumps(capabilities)))
        except sqlite3.IntegrityError as error:
            if "model_profiles.user_id, model_profiles.name" in str(error):
                raise DuplicateModelProfileError("A profile with this name already exists") from error
            raise
        return profile_id

    def delete(self, user_id: str, profile_id: str) -> bool:
        with self._connect() as c:
            return c.execute("DELETE FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id)).rowcount > 0


user_model_profiles = UserModelProfileRepository()
