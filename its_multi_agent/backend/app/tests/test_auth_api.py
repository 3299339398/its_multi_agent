import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from its_multi_agent.backend.app.api import dependencies, routers
from its_multi_agent.backend.app.api.main import create_fast_api
from its_multi_agent.backend.app.repositories.user_repository import UserRepository
from its_multi_agent.backend.app.services.auth_service import AuthService


class AuthApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = UserRepository(str(Path(self.temp_dir.name) / "users.db"))
        service = AuthService(
            repository=repository,
            secret="api-test-secret-that-is-at-least-32-characters",
            bootstrap_users_json=json.dumps([
                {
                    "user_id": "user-1",
                    "username": "root1",
                    "password": "correct-password",
                    "role": "user",
                },
                {
                    "user_id": "admin-1",
                    "username": "admin1",
                    "password": "admin-password",
                    "role": "admin",
                },
            ]),
        )
        routers.auth_service = service
        dependencies.auth_service = service
        self.client = TestClient(create_fast_api())

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def test_protected_endpoint_rejects_missing_token(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_public_registration_creates_regular_user_and_logs_them_in(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "client1", "password": "client-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"], {
            "user_id": "client1", "username": "client1", "role": "user",
        })
        current = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
        self.assertEqual(current.status_code, 200)

    def test_registration_cannot_create_admin_and_rejects_duplicate(self):
        first = self.client.post(
            "/api/auth/register",
            json={"username": "client2", "password": "client-password", "role": "admin"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["user"]["role"], "user")
        duplicate = self.client.post(
            "/api/auth/register",
            json={"username": "client2", "password": "another-password"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_login_token_identifies_current_user(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "root1", "password": "correct-password"},
        )
        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]

        current_user = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(current_user.status_code, 200)
        self.assertEqual(
            current_user.json()["user"],
            {"user_id": "user-1", "username": "root1", "role": "user"},
        )

    def test_regular_user_cannot_upload_knowledge(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "root1", "password": "correct-password"},
        )
        response = self.client.post(
            "/api/knowledge/upload",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            files={"file": ("sample.txt", b"content", "text/plain")},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_user_can_upload_knowledge(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "admin1", "password": "admin-password"},
        )
        forwarded = AsyncMock(return_value={"status": "success"})
        with patch.object(routers, "_forward_knowledge_request", forwarded):
            response = self.client.post(
                "/api/knowledge/upload",
                headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                files={"file": ("sample.txt", b"content", "text/plain")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})
        forwarded.assert_awaited_once()

    def test_regular_user_cannot_list_knowledge_documents(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "root1", "password": "correct-password"},
        )

        response = self.client.get(
            "/api/knowledge/documents",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_and_delete_knowledge_documents(self):
        login = self.client.post(
            "/api/auth/login",
            json={"username": "admin1", "password": "admin-password"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        document_hash = "a" * 64
        forwarded = AsyncMock(return_value={"status": "ok"})

        with patch.object(routers, "_forward_knowledge_request", forwarded):
            listed = self.client.get("/api/knowledge/documents", headers=headers)
            deleted = self.client.delete(
                f"/api/knowledge/documents/{document_hash}", headers=headers,
            )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(forwarded.await_count, 2)
        delete_call = forwarded.await_args_list[1]
        self.assertEqual(delete_call.args[0], f"/documents/{document_hash}")
        self.assertEqual(delete_call.kwargs["method"], "DELETE")
        self.assertEqual(delete_call.kwargs["headers"], {"X-Actor-Id": "admin1"})


if __name__ == "__main__":
    unittest.main()
