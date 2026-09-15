import unittest
from its_multi_agent.backend.app.services.query_rewriter import rewrite_query

class QueryRewriterTest(unittest.TestCase):
    history = [{"role":"user","content":"华为 Mate 60 怎么样？"}]
    def test_short_followup_is_standalone(self):
        self.assertIn("Mate 60", rewrite_query("续航呢？", self.history))
    def test_pronoun_is_standalone(self):
        self.assertIn("华为", rewrite_query("它的价格？", self.history))
    def test_missing_context_is_unchanged(self):
        self.assertEqual(rewrite_query("续航呢？", []), "续航")
    def test_normal_question_is_unchanged(self):
        self.assertEqual(rewrite_query("北京天气", self.history), "北京天气")

if __name__ == "__main__": unittest.main()
