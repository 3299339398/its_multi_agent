import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from its_multi_agent.backend.app.services.file_artifact_service import FileArtifactError, FileArtifactService


class FileArtifactTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FileArtifactService(self.temp.name)

    def test_create_get_and_delete_is_user_scoped(self):
        item = self.service.create("alice", "report.md", "# Result", mime_type="text/markdown", session_id="s1")
        loaded = self.service.get("alice", item["id"])
        self.assertEqual(loaded["filename"], "report.md")
        self.assertEqual(loaded["path"].read_text(encoding="utf-8"), "# Result")
        with self.assertRaises(FileArtifactError):
            self.service.get("bob", item["id"])
        self.assertTrue(self.service.delete("alice", item["id"]))
        with self.assertRaises(FileArtifactError):
            self.service.get("alice", item["id"])

    def test_rejects_path_traversal_types_and_mismatched_mime(self):
        for filename in ("../report.md", "run.py", "report.zip"):
            with self.assertRaises(FileArtifactError):
                self.service.create("alice", filename, "x", mime_type="text/markdown")
        with self.assertRaises(FileArtifactError):
            self.service.create("alice", "report.md", "x", mime_type="text/plain")
        with self.assertRaises(FileArtifactError):
            self.service.delete("alice", "../metadata")

    def test_list_filters_by_session(self):
        self.service.create("alice", "a.txt", "a", session_id="s1")
        self.service.create("alice", "b.txt", "b", session_id="s2")
        self.assertEqual([item["filename"] for item in self.service.list("alice", session_id="s1")], ["a.txt"])


class PreviewSecurityTest(unittest.TestCase):
    def test_html_preview_is_signed_and_sandboxed_while_download_stays_attachment(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from its_multi_agent.backend.app.api import routers
        from its_multi_agent.backend.app.services.file_preview_service import settings
        with tempfile.TemporaryDirectory() as folder:
            service = FileArtifactService(folder)
            item = service.create("alice", "animation.html", "<script>window.test=1</script>", mime_type="text/html")
            app = FastAPI()
            app.include_router(routers.router)
            app.dependency_overrides[routers.get_current_user] = lambda: {"user_id": "alice"}
            with patch.object(routers, "file_artifact_service", service), patch.object(settings, "AUTH_JWT_SECRET", "offline-preview-signing-secret-32-characters"), TestClient(app) as client:
                ticket = client.post(f"/api/files/{item['id']}/preview-ticket")
                self.assertEqual(ticket.status_code, 200)
                response = client.get(ticket.json()["preview_url"])
                self.assertEqual(response.status_code, 200)
                policy = response.headers["content-security-policy"]
                self.assertIn("sandbox allow-scripts;", policy)
                self.assertNotIn("allow-same-origin", policy)
                self.assertIn("connect-src 'none'", policy)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(client.get("/api/file-previews/invalid").status_code, 404)
                download = client.get(f"/api/files/{item['id']}/download")
                self.assertTrue(download.headers["content-disposition"].startswith("attachment"))

    def test_preview_signature_rejects_tampering_and_expiration(self):
        from unittest.mock import patch
        from its_multi_agent.backend.app.services import file_preview_service as preview
        with patch.object(preview.settings, "AUTH_JWT_SECRET", "offline-preview-signing-secret-32-characters"):
            with patch.object(preview.time, "time", return_value=100):
                ticket = preview.issue_preview_ticket("user", "artifact")
                self.assertEqual(preview.verify_preview_ticket(ticket), ("user", "artifact"))
                with self.assertRaises(ValueError):
                    preview.verify_preview_ticket(ticket[:-1] + ("0" if ticket[-1] != "0" else "1"))
            with patch.object(preview.time, "time", return_value=401):
                with self.assertRaises(ValueError):
                    preview.verify_preview_ticket(ticket)


if __name__ == "__main__":
    unittest.main()
