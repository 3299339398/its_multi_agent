import json
import tempfile
import unittest

import jwt
from pathlib import Path

from its_multi_agent.backend.app.repositories.user_repository import UserRepository
from its_multi_agent.backend.app.services.auth_service import AuthService


class AuthServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = UserRepository(str(Path(self.temp_dir.name) / "users.db"))
        bootstrap = json.dumps([
            {
                "user_id": "user-1",
                "username": "root1",
                "password": "correct-password",
                "role": "admin",
            }
        ])
        self.service = AuthService(
            repository=self.repository,
            secret="test-secret-that-is-at-least-32-characters-long",
            token_ttl_minutes=60,
            bootstrap_users_json=bootstrap,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_authenticates_and_decodes_token(self):
        user = self.service.authenticate("root1", "correct-password")
        self.assertEqual(
            user,
            {"user_id": "user-1", "username": "root1", "role": "admin"},
        )

        token = self.service.issue_token(user)
        self.assertEqual(self.service.decode_token(token), user)

    def test_role_change_invalidates_existing_tokens(self):
        user = self.service.authenticate("root1", "correct-password")
        token = self.service.issue_token(user)
        self.repository.update_role("user-1", "user")
        with self.assertRaises(jwt.InvalidTokenError):
            self.service.decode_token(token)

    def test_rejects_wrong_password(self):
        self.assertIsNone(self.service.authenticate("root1", "wrong-password"))

    def test_password_hash_is_salted(self):
        first = self.service.hash_password("correct-password")
        second = self.service.hash_password("correct-password")
        self.assertNotEqual(first, second)
        self.assertTrue(self.service.verify_password("correct-password", first))


if __name__ == "__main__":
    unittest.main()
