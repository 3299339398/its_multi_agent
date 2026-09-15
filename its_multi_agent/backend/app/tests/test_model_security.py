import base64
import asyncio
import hashlib
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
import httpx
from openai import APIStatusError, DefaultAsyncHttpxClient

from its_multi_agent.backend.app.infrastructure.ai import model_factory
from its_multi_agent.backend.app.repositories import model_profile_repository as repository


def configuration(**overrides):
    values = dict(AUTH_JWT_SECRET="old-jwt", MODEL_PROFILE_ENCRYPTION_KEY=None,
                  MODEL_PROFILE_ENCRYPTION_KEY_PATH=None, MODEL_PROFILE_LEGACY_JWT_SECRET=None,
                  MODEL_ALLOWED_BASE_URLS_JSON='["https://example.test/v1"]',
                  MODEL_PROFILES_JSON="", SF_BASE_URL=None, AL_BAILIAN_BASE_URL=None)
    values.update(overrides)
    return SimpleNamespace(**values)


class ModelSecurityTest(unittest.TestCase):
    def test_arbitrary_endpoints_are_rejected_before_client_creation(self):
        with patch.object(model_factory, "settings", configuration()), patch.object(model_factory, "AsyncOpenAI") as client:
            for endpoint in ("http://127.0.0.1/v1", "http://169.254.169.254/latest", "https://evil.test/v1",
                             "https://example.test/v1/../../internal", "https://user:pass@example.test/v1",
                             "https://example.test/v1?target=internal"):
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    model_factory.create_model("temporary", "test", endpoint, "test-key")
            client.assert_not_called()

    def test_administrator_local_endpoint_is_allowed_without_redirects(self):
        config = configuration(MODEL_ALLOWED_BASE_URLS_JSON='["http://localhost:11434/v1"]')
        with patch.object(model_factory, "settings", config), patch.object(model_factory, "AsyncOpenAI") as client:
            model_factory.create_model("temporary", "test", "http://LOCALHOST:11434/v1/", "test-key")
        self.assertEqual(client.call_args.kwargs["base_url"], "http://localhost:11434/v1")
        self.assertFalse(client.call_args.kwargs["http_client"].follow_redirects)

    def test_redirect_cannot_send_credentials_to_an_unapproved_endpoint(self):
        visited = []

        def redirect(request):
            visited.append(str(request.url))
            return httpx.Response(307, headers={"location": "http://169.254.169.254/latest"})

        async def request():
            transport = httpx.MockTransport(redirect)
            client = DefaultAsyncHttpxClient(transport=transport, follow_redirects=False)
            with patch.object(model_factory, "settings", configuration()), patch.object(model_factory, "DefaultAsyncHttpxClient", return_value=client):
                model = model_factory.create_model("temporary", "test", "https://example.test/v1", "test-key")
            try:
                with self.assertRaises(APIStatusError):
                    await model._client.chat.completions.create(model="test", messages=[{"role": "user", "content": "hello"}])
            finally:
                await model._client.close()

        asyncio.run(request())
        self.assertEqual(visited, ["https://example.test/v1/chat/completions"])

    def test_configured_server_endpoints_are_approved(self):
        from its_multi_agent.backend.app.services.model_endpoint_policy import validate_model_base_url
        config = configuration(MODEL_PROFILES_JSON=json.dumps([{"base_url": "https://SERVER.test:443/v1/"}]))
        self.assertEqual(validate_model_base_url("https://server.test/v1", config), "https://server.test/v1")

    def test_repository_refuses_unapproved_profiles(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repository, "settings", configuration()):
            repo = repository.UserModelProfileRepository(str(Path(directory) / "profiles.db"))
            with self.assertRaises(ValueError):
                repo.save("user", dict(name="Bad", model_name="test", base_url="http://127.0.0.1/v1", api_key="test-key"))
            self.assertEqual(repo.list_public("user"), [])

    def test_concurrent_initialization_shares_one_durable_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repository, "settings", configuration()):
            path = str(Path(directory) / "profiles.db")

            def save(index):
                repo = repository.UserModelProfileRepository(path)
                return repo.save("user", dict(name=str(index), model_name="test", base_url="https://example.test/v1", api_key="test-key"))

            with ThreadPoolExecutor(max_workers=4) as pool:
                ids = list(pool.map(save, range(4)))
            repo = repository.UserModelProfileRepository(path)
            self.assertEqual([repo.get("user", profile_id)["api_key"] for profile_id in ids], ["test-key"] * 4)

    def test_saved_credentials_survive_jwt_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "profiles.db")
            with patch.object(repository, "settings", configuration()):
                repo = repository.UserModelProfileRepository(path)
                profile_id = repo.save("user", dict(name="One", model_name="test", base_url="https://example.test/v1", api_key="test-key"))
            with patch.object(repository, "settings", configuration(AUTH_JWT_SECRET="new-jwt")):
                reopened = repository.UserModelProfileRepository(path)
                self.assertEqual(reopened.get("user", profile_id)["api_key"], "test-key")

    def test_legacy_credentials_migrate_before_jwt_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.db"
            old_cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"old-jwt").digest()))
            token = old_cipher.encrypt(b"legacy-key").decode()
            self._legacy_database(path, token)
            with patch.object(repository, "settings", configuration()):
                repository.UserModelProfileRepository(str(path))
            with patch.object(repository, "settings", configuration(AUTH_JWT_SECRET="new-jwt")):
                reopened = repository.UserModelProfileRepository(str(path))
                self.assertEqual(reopened.get("user", "legacy")["api_key"], "legacy-key")
            with closing(sqlite3.connect(path)) as connection:
                self.assertNotEqual(connection.execute("SELECT api_key FROM model_profiles").fetchone()[0], token)

    def test_unreadable_legacy_credentials_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.db"
            self._legacy_database(path, "unreadable")
            with patch.object(repository, "settings", configuration()), self.assertRaisesRegex(RuntimeError, "credentials"):
                repository.UserModelProfileRepository(str(path))
            self.assertFalse(path.with_suffix(".db.key").exists())
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT api_key FROM model_profiles").fetchone()[0], "unreadable")

    def test_previous_jwt_can_migrate_credentials_into_an_explicit_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.db"
            legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"old-jwt").digest()))
            self._legacy_database(path, legacy.encrypt(b"legacy-key").decode())
            key = Fernet.generate_key().decode()
            config = configuration(AUTH_JWT_SECRET="new-jwt", MODEL_PROFILE_ENCRYPTION_KEY=key,
                                   MODEL_PROFILE_LEGACY_JWT_SECRET="old-jwt")
            with patch.object(repository, "settings", config):
                repo = repository.UserModelProfileRepository(str(path))
                self.assertEqual(repo.get("user", "legacy")["api_key"], "legacy-key")
            self.assertFalse(path.with_suffix(".db.key").exists())
            with patch.object(repository, "settings", configuration(AUTH_JWT_SECRET="another-jwt", MODEL_PROFILE_ENCRYPTION_KEY=key)):
                repo = repository.UserModelProfileRepository(str(path))
                self.assertEqual(repo.get("user", "legacy")["api_key"], "legacy-key")

    def test_lost_independent_key_fails_without_generating_a_replacement(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repository, "settings", configuration()):
            path = Path(directory) / "profiles.db"
            repo = repository.UserModelProfileRepository(str(path))
            repo.save("user", dict(name="One", model_name="test", base_url="https://example.test/v1", api_key="test-key"))
            path.with_suffix(".db.key").unlink()
            with self.assertRaisesRegex(RuntimeError, "credentials"):
                repository.UserModelProfileRepository(str(path))
            self.assertFalse(path.with_suffix(".db.key").exists())

    def test_empty_key_file_fails_clearly_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(repository, "settings", configuration()):
            path = Path(directory) / "profiles.db"
            key_path = path.with_suffix(".db.key")
            key_path.touch()
            with self.assertRaisesRegex(RuntimeError, "credentials encryption key"):
                repository.UserModelProfileRepository(str(path))
            self.assertEqual(key_path.read_bytes(), b"")

    @staticmethod
    def _legacy_database(path, token):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE model_profiles (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,provider TEXT NOT NULL,model_name TEXT NOT NULL,base_url TEXT NOT NULL,api_key TEXT NOT NULL,roles TEXT NOT NULL,created_at TEXT NOT NULL, UNIQUE(user_id,name))")
            connection.execute("INSERT INTO model_profiles VALUES ('legacy','user','Old','test','test','https://example.test/v1',?,'chat','now')", (token,))
            connection.commit()
