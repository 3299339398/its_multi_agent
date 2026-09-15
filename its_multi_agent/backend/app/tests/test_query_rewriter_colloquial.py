import unittest
from its_multi_agent.backend.app.services.query_rewriter import rewrite_query

class ColloquialRewriteTest(unittest.TestCase):
    def test_normalizes_across_domains_without_history(self):
        self.assertEqual(rewrite_query("嗯，帮我看下这个报错呢？"), "请分析这个报错")
        self.assertEqual(rewrite_query("请问一下有啥办法啊"), "有哪些办法")
        self.assertEqual(rewrite_query("那个，咋办呀"), "如何处理")

if __name__ == "__main__": unittest.main()
