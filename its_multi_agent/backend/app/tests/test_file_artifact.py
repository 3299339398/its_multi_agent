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


if __name__ == "__main__":
    unittest.main()
