import json
import unittest
from types import SimpleNamespace

from its_multi_agent.backend.app.services.context_budget import ContextBudgeter, TokenLimits


class ContextBudgetRegressionTest(unittest.TestCase):
    def test_fork_keeps_current_image_and_crops_actual_technical_fields(self):
        query = "分析这张图"
        messages = [
            {"role": "user", "content": "old history " * 4000},
            {"role": "user", "content": [
                {"type": "input_text", "text": query},
                {"type": "input_image", "image_url": "data:image/png;base64,AA=="},
            ]},
            {"role": "user", "content": json.dumps({
                "type": "fork_branch", "role": "technical", "task": "分析", "instructions": "核对证据",
                "data": {"query": query, "reviewed_sources": [
                    {"source_id": str(i), "excerpt": "证据正文" * 3000} for i in range(8)
                ], "dependencies": {"prior": {"status": "completed", "answer": "依赖结果" * 5000}}},
            }, ensure_ascii=False)},
        ]
        fitted, report = ContextBudgeter().fit(
            messages, agent=SimpleNamespace(instructions="", tools=[]), model_name="offline",
            limits=TokenLimits(4096, 512, 256), protected_query=query, protected_message_index=1,
        )
        self.assertTrue(any(isinstance(m["content"], list) and any(
            part.get("type") == "input_image" for part in m["content"]
        ) for m in fitted))
        self.assertLessEqual(report.estimated_input_tokens, report.input_budget)
        self.assertGreater(report.truncated_evidence, 0)
        self.assertIn("核对证据", fitted[-1]["content"])
        # Budgeting must not mutate the shared prefix or the source evidence.
        self.assertEqual(len(json.loads(messages[-1]["content"])["data"]["reviewed_sources"]), 8)
