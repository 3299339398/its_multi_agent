import tempfile
import time
import unittest
from pathlib import Path

from its_multi_agent.backend.app.repositories.sqlite_memory_repository import (
    SQLiteMemoryRepository,
)
from its_multi_agent.backend.app.services.memory_service import MemoryService


class SQLiteMemoryRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = SQLiteMemoryRepository(
            str(Path(self.temp_dir.name) / "memories.db")
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def memory(self, content="我喜欢安静的酒店", importance=0.8):
        now = int(time.time())
        return {
            "user_id": "user-1",
            "content": content,
            "memory_type": "preference",
            "importance": importance,
            "source_session_id": "session-1",
            "created_at": now,
            "expires_at": now + 86400,
        }

    def test_insert_list_and_delete(self):
        memory_id = int(self.repository.upsert_or_insert(self.memory()))
        rows = self.repository.list("user-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "我喜欢安静的酒店")
        self.assertTrue(self.repository.delete("user-1", memory_id))
        self.assertEqual(self.repository.list("user-1"), [])

    def test_duplicate_content_is_updated_not_duplicated(self):
        first_id = self.repository.upsert_or_insert(self.memory(importance=0.6))
        second_id = self.repository.upsert_or_insert(self.memory(importance=0.9))
        self.assertEqual(first_id, second_id)
        rows = self.repository.list("user-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["importance"], 0.9)

    def test_text_search_prefers_related_memory(self):
        self.repository.upsert_or_insert(self.memory("我使用的是 ThinkPad X1", 0.7))
        self.repository.upsert_or_insert(self.memory("我喜欢安静的酒店", 0.7))
        rows = self.repository.search_text("user-1", "帮我推荐住宿酒店", limit=2)
        self.assertEqual(rows[0]["content"], "我喜欢安静的酒店")


class LocalMemoryExtractionTest(unittest.TestCase):
    def test_extracts_explicit_profile_preference_and_device(self):
        memories = MemoryService.extract_local_memories(
            "我叫小王。我喜欢安静的酒店。我的电脑是 ThinkPad X1。"
        )
        self.assertEqual(
            {item["memory_type"] for item in memories},
            {"profile", "preference", "device"},
        )

    def test_ignores_ordinary_question(self):
        self.assertEqual(
            MemoryService.extract_local_memories("北京到上海怎么走？"),
            [],
        )

    def test_explicit_remember_request_is_stored_once(self):
        memories = MemoryService.extract_local_memories("请记住我喜欢靠窗的座位")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["memory_type"], "fact")


if __name__ == "__main__":
    unittest.main()
