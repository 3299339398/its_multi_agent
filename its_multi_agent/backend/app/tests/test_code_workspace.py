import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.app.services.code_workspace_service import (
    CodeWorkspaceError,
    CodeWorkspaceService,
)
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext
from its_multi_agent.backend.app.services.agent_service import coding_enabled_for_request


class CodeWorkspaceServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("value = 1\nprint(value)\n", encoding="utf-8")
        db_patch = patch.object(CodeWorkspaceService, "_operation_db", return_value=self.root / "operations.db")
        db_patch.start()
        self.addCleanup(db_patch.stop)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.root / "operations.db")) as db, db:
            db.execute("CREATE TABLE operations (operation_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at REAL NOT NULL)")
        self.service = CodeWorkspaceService(self.root)

    def test_read_search_replace_and_create_stay_in_workspace(self):
        read = self.service.read_file("src/app.py", 1, 2)
        self.assertIn("1: value = 1", read["content"])
        found = self.service.search("print(value)")
        self.assertEqual(found["matches"][0]["path"], "src/app.py")

        changed = self.service.replace("src/app.py", "value = 1", "value = 2")
        self.assertIn("+value = 2", changed["diff"])
        created = self.service.create("src/new.py", "answer = 42\n")
        self.assertTrue(created["changed"])
        self.assertEqual((self.root / "src/new.py").read_text(encoding="utf-8"), "answer = 42\n")

    def test_path_escape_secret_files_and_ambiguous_replacement_are_rejected(self):
        for path in ("../outside.py", ".git/config", "local.env"):
            with self.subTest(path=path), self.assertRaises(CodeWorkspaceError):
                self.service.read_file(path)
        (self.root / "src/app.py").write_text("same\nsame\n", encoding="utf-8")
        with self.assertRaisesRegex(CodeWorkspaceError, "匹配 2 次"):
            self.service.replace("src/app.py", "same", "other")

    def test_only_administrator_defined_checks_can_run(self):
        command = ["python", "-c", "print('check-ok')"]
        with patch(
            "its_multi_agent.backend.app.services.code_workspace_service.settings.CODE_CHECK_COMMANDS_JSON",
            json.dumps({"unit": command}),
        ):
            result = self.service.run_check("unit")
            self.assertEqual(result["status"], "ok")
            self.assertIn("check-ok", result["output"])
            with self.assertRaises(CodeWorkspaceError):
                self.service.run_check("python -c unsafe")

    def test_replace_checks_version_and_replays_idempotent_operation(self):
        original = (self.root / "src/app.py").read_text(encoding="utf-8")
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        changed = self.service.replace(
            "src/app.py", "value = 1", "value = 2", expected_sha256=digest, operation_id="op-test-1",
        )
        replay = self.service.replace(
            "src/app.py", "value = 1", "value = 2", expected_sha256=digest, operation_id="op-test-1",
        )
        self.assertEqual(changed["after_sha256"], replay["after_sha256"])
        self.assertTrue(replay["idempotent_replay"])
        with self.assertRaisesRegex(CodeWorkspaceError, "版本已变化"):
            self.service.replace("src/app.py", "value = 2", "value = 3", expected_sha256=digest)

    def test_concurrent_replacements_of_same_version_have_only_one_winner(self):
        digest = self.service.read_file("src/app.py")["sha256"]
        barrier = threading.Barrier(2)
        def change(value):
            barrier.wait()
            try:
                self.service.replace("src/app.py", "value = 1", f"value = {value}", expected_sha256=digest)
                return True
            except CodeWorkspaceError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(change, [2, 3]))
        self.assertEqual(sum(outcomes), 1)

    def test_operation_id_is_scoped_and_rejects_changed_request(self):
        digest = self.service.read_file("src/app.py")["sha256"]
        self.service.replace("src/app.py", "value = 1", "value = 2", expected_sha256=digest, operation_id="same")
        other = self.root / "other"
        other.mkdir()
        (other / "app.py").write_text("value = 1\nprint(value)\n", encoding="utf-8")
        service = CodeWorkspaceService(other)
        result = service.replace("app.py", "value = 1", "value = 2", expected_sha256=digest, operation_id="same")
        self.assertFalse(result.get("idempotent_replay", False))
        with self.assertRaisesRegex(CodeWorkspaceError, "其他修改请求"):
            self.service.replace("src/app.py", "value = 2", "value = 3", operation_id="same")

    def test_coding_requires_explicit_request_and_server_workspace(self):
        context = UserContext(session_id="test")
        implicit = ChatMessageRequest(query="修改代码", context=context)
        explicit = ChatMessageRequest(query="修改代码", context=context, enabled_plugins=["coding"])
        with patch(
            "its_multi_agent.backend.app.services.agent_service.settings.CODE_WORKSPACE_ROOT",
            str(self.root),
        ):
            self.assertFalse(coding_enabled_for_request(implicit))
            self.assertTrue(coding_enabled_for_request(explicit))
        with patch(
            "its_multi_agent.backend.app.services.agent_service.settings.CODE_WORKSPACE_ROOT",
            None,
        ):
            self.assertFalse(coding_enabled_for_request(explicit))


if __name__ == "__main__":
    unittest.main()
