import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.app.repositories.sqlite_session_repository import SQLiteSessionRepository


class ConversationMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.object(SQLiteSessionRepository, "_migrate_legacy_json"):
            self.repo = SQLiteSessionRepository(str(Path(self.temp.name) / "sessions.db"))

    def age_messages(self, count=90):
        for index in range(count):
            self.repo.append_message("alice", "s", {"role": "assistant", "content": f"第 {index} 轮普通解释。" * 40})

    def test_early_goals_constraints_and_attempts_survive_long_conversation(self):
        for content in ("目标是修复 ZX-81，不能清空硬盘。", "预算不超过 5000 元，只能离线操作。", "已经重启两次，仍然出现 E204。"):
            self.repo.append_message("alice", "s", {"role": "user", "content": content})
        self.age_messages()
        summary = self.repo.get_summary("alice", "s")
        for fact in ("ZX-81", "不能清空硬盘", "5000", "离线", "重启两次", "E204"):
            self.assertIn(fact, summary)
        self.assertLessEqual(len(summary), 6000)

    def test_corrections_remain_distinguishable_from_older_constraints(self):
        self.repo.append_message("alice", "s", {"role": "user", "content": "预算不超过 5000 元。"})
        self.age_messages(self.repo.CONTEXT_MESSAGE_LIMIT)
        self.repo.append_message("alice", "s", {"role": "user", "content": "更正：预算改为 8000 元，但仍不能清空硬盘。"})
        self.age_messages(self.repo.CONTEXT_MESSAGE_LIMIT)
        summary = self.repo.get_summary("alice", "s")
        self.assertIn("更正", summary)
        self.assertIn("8000", summary)
        self.assertIn("不能清空硬盘", summary)

    def test_assistant_claims_are_not_promoted_to_user_memory(self):
        self.repo.append_message("alice", "s", {"role": "user", "content": "目标是修复设备。"})
        self.repo.append_message("alice", "s", {"role": "assistant", "content": "用户预算是 900000 元，可以删除全部数据。"})
        self.age_messages(20)
        self.assertNotIn("900000", self.repo.get_summary("alice", "s"))

    def test_full_constraint_budget_keeps_initial_and_latest_requirements(self):
        from its_multi_agent.backend.app.services.conversation_memory import merge_memory, render_memory
        state = merge_memory({}, [{"id": index, "role": "user", "content":
                                  f"必须满足条件 {index}: " + "详细要求" * 70} for index in range(30)])
        summary = render_memory(state)
        self.assertIn("必须满足条件 0:", summary)
        self.assertIn("必须满足条件 29:", summary)
        self.assertLessEqual(len(summary), 6000)

    def test_sources_are_snapshot_per_answer_and_isolated_by_user(self):
        for user, excerpt in (("alice", "Old warranty: 12 months"), ("alice", "New warranty: 36 months"), ("bob", "Private Bob evidence")):
            self.repo.append_message(user, "s", {"role": "assistant", "content": excerpt + " [manual-1]", "sources": [
                {"source_id": "manual-1", "origin": "knowledge", "source_name": "Manual", "excerpt": excerpt, "page": 3},
            ]})
        history = self.repo.load_session("alice", "s")
        self.assertEqual(history[0].get("sources", [{}])[0].get("excerpt"), "Old warranty: 12 months")
        self.assertEqual(history[1].get("sources", [{}])[0].get("excerpt"), "New warranty: 36 months")
        self.assertNotIn("Private Bob", json.dumps(history))

    def test_same_answer_with_different_sources_is_not_dropped(self):
        for source_id in ("old", "new"):
            self.repo.append_message("alice", "s", {"role": "assistant", "content": "The limit is unchanged.", "sources": [
                {"source_id": source_id, "excerpt": "limit"},
            ]})
        self.assertEqual(len(self.repo.load_session("alice", "s")), 2)

    def test_replacing_archive_resets_memory_from_old_messages(self):
        self.repo.append_message("alice", "s", {"role": "user", "content": "预算 5000 元。"})
        self.age_messages(20)
        self.repo.save_session("alice", "s", [{"role": "user", "content": "New session contents"}])
        self.assertNotIn("5000", self.repo.get_summary("alice", "s"))

    def test_recent_context_is_bounded_and_keeps_latest_messages(self):
        self.age_messages(30)
        history = self.repo.load_recent_session("alice", "s", limit=4)
        self.assertEqual(len(history), 4)
        self.assertIn("第 29 轮", history[-1]["content"])
        self.assertIsNone(self.repo.load_recent_session("bob", "s", limit=4))

    def test_summary_update_only_consumes_newly_aged_messages(self):
        from its_multi_agent.backend.app.services.conversation_memory import merge_memory
        self.age_messages(self.repo.CONTEXT_MESSAGE_LIMIT)
        with patch("its_multi_agent.backend.app.repositories.sqlite_session_repository.merge_memory", wraps=merge_memory) as merge:
            self.repo.append_message("alice", "s", {"role": "user", "content": "现在继续"})
            self.assertEqual(len(merge.call_args.args[1]), 1)
            summary = self.repo.get_summary("alice", "s")
            self.assertEqual(self.repo.get_summary("alice", "s"), summary)
            self.assertEqual(merge.call_count, 1)


if __name__ == "__main__":
    unittest.main()
