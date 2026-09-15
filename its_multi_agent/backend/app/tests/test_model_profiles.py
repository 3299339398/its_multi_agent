import tempfile
import sqlite3
import unittest
import base64
import hashlib
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet

from its_multi_agent.backend.app.schemas import model_profile
from its_multi_agent.backend.app.repositories.model_profile_repository import UserModelProfileRepository
from its_multi_agent.backend.app.config.settings import Settings, settings


class ModelProfileTest(unittest.TestCase):
    def setUp(self):
        allowed = patch.object(settings, "MODEL_ALLOWED_BASE_URLS_JSON", '["https://example.test", "https://example.test/v1"]')
        allowed.start()
        self.addCleanup(allowed.stop)

    def test_legacy_schema_migrates_and_preserves_inferred_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.db")
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE model_profiles (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,provider TEXT NOT NULL,model_name TEXT NOT NULL,base_url TEXT NOT NULL,api_key TEXT NOT NULL,roles TEXT NOT NULL,created_at TEXT NOT NULL, UNIQUE(user_id,name))")
                legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256((settings.AUTH_JWT_SECRET or "").encode()).digest()))
                connection.execute("INSERT INTO model_profiles VALUES ('old','user','Old','test','test','https://example.test',?,'chat,vision','now')", (legacy.encrypt(b"test-key").decode(),))
            connection.close()
            repo = UserModelProfileRepository(path)
            public = repo.list_public("user")[0]
            self.assertTrue(public["supports_tools"])
            self.assertTrue(public["supports_vision"])
            self.assertFalse(public["supports_reasoning"])

    def test_duplicate_name_returns_conflict_and_credentials_stay_private(self):
        from fastapi import HTTPException
        from its_multi_agent.backend.app.api.routers import save_model_profile
        dto = model_profile.ModelProfileCreate(name="same", model_name="test", base_url="https://example.test", api_key="test-key")
        with tempfile.TemporaryDirectory() as directory:
            repo = UserModelProfileRepository(str(Path(directory) / "profiles.db"))
            with patch("its_multi_agent.backend.app.api.routers.user_model_profiles", repo):
                save_model_profile(dto, {"user_id": "user"})
                with self.assertRaises(HTTPException) as raised:
                    save_model_profile(dto, {"user_id": "user"})
                self.assertEqual(raised.exception.status_code, 409)
            self.assertNotIn("api_key", repo.list_public("user")[0])
            self.assertNotIn(b"test-key", repo.path.read_bytes())

    def test_default_model_uses_json_profile_without_legacy_suppliers(self):
        import json
        from types import SimpleNamespace
        from its_multi_agent.backend.app.infrastructure.ai import model_factory
        config = SimpleNamespace(MODEL_PROFILES_JSON=json.dumps([dict(id="json-default", name="Json", model_name="json-model", base_url="https://example.test", api_key="test-key")]),
                                 SF_API_KEY=None, AL_BAILIAN_API_KEY=None)
        with patch.object(model_factory, "settings", config), patch.object(model_factory, "create_model") as create:
            model_factory.default_model()
        self.assertEqual(create.call_args.args[:2], ("json-default", "json-model"))

    def test_personal_input_needs_no_id_and_capabilities_roundtrip(self):
        dto = model_profile.ModelProfileCreate(
            name="personal", model_name="test", base_url="https://example.test/v1",
            api_key="test-key", roles=("chat", "vision"), supports_tools=False,
            supports_vision=True, supports_reasoning=True, supports_streaming=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            repo = UserModelProfileRepository(str(Path(directory) / "profiles.db"))
            profile_id = repo.save("user", dto.model_dump())
            self.assertTrue(profile_id.startswith("user-"))
            for item in [repo.get("user", profile_id), repo.list_public("user")[0]]:
                for field in ("roles", "supports_tools", "supports_vision", "supports_reasoning", "supports_streaming"):
                    self.assertEqual(item[field], getattr(dto, field))
            self.assertIsNone(repo.get("other", profile_id))

    def test_json_only_configuration_is_valid(self):
        settings = Settings(_env_file=None, SF_API_KEY=None, AL_BAILIAN_API_KEY=None,
                            MODEL_PROFILES_JSON='[{"id":"one","name":"One","model_name":"test","base_url":"https://example.test","api_key":"test-key"}]')
        self.assertTrue(settings.MODEL_PROFILES_JSON)

    def test_invalid_json_profiles_rejected_at_configuration(self):
        with self.assertRaises(ValueError):
            Settings(_env_file=None, SF_API_KEY="test", SF_BASE_URL="https://example.test", MODEL_PROFILES_JSON='{}')
