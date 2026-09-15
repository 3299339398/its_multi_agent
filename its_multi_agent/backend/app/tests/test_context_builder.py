import unittest

from its_multi_agent.backend.app.services.context_builder import ContextBuilder


class FakeRepository:
    def get_summary(self, user_id, session_id):
        return "较早对话摘要"


class FakeCache:
    def __init__(self):
        self.value = None

    def get(self, user_id, session_id):
        return self.value

    def set(self, user_id, session_id, context):
        self.value = context


class ContextBuilderTest(unittest.TestCase):
    def setUp(self):
        self.cache = FakeCache()
        self.builder = ContextBuilder(FakeRepository(), self.cache)
        self.history = [{"role": "system", "content": "system"}] + [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"message-{index}"}
            for index in range(16)
        ]

    def test_builds_summary_and_recent_messages(self):
        context = self.builder.build("root1", "session1", self.history, max_turn=3)

        self.assertEqual(context[0]["content"], "system")
        self.assertIn("较早对话摘要", context[1]["content"])
        self.assertEqual([item["content"] for item in context[-6:]], [f"message-{i}" for i in range(10, 16)])

    def test_returns_cached_context_until_forced(self):
        first = self.builder.build("root1", "session1", self.history, max_turn=3)
        changed = self.history + [{"role": "user", "content": "new-message"}]

        self.assertIs(self.builder.build("root1", "session1", changed, max_turn=3), first)
        refreshed = self.builder.build("root1", "session1", changed, max_turn=3, force_refresh=True)
        self.assertEqual(refreshed[-1]["content"], "new-message")

    def test_appends_user_message_to_existing_cache(self):
        self.builder.build(
            "root1", "session1", self.history, max_turn=3,
            memory_context="旧长期记忆",
        )
        context = self.builder.append_user_message(
            "root1", "session1", "current-question", max_turn=3,
            memory_context="新长期记忆",
        )
        self.assertEqual(context[-1]["content"], "current-question")
        contents = [item["content"] for item in context]
        self.assertEqual(sum(content.startswith(self.builder.SUMMARY_PREFIX) for content in contents), 1)
        self.assertEqual(sum(content.startswith(self.builder.MEMORY_PREFIX) for content in contents), 1)
        self.assertNotIn(self.builder.MEMORY_PREFIX + "旧长期记忆", contents)
        self.assertIn(self.builder.MEMORY_PREFIX + "新长期记忆", contents)


if __name__ == "__main__":
    unittest.main()
