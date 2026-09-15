import unittest

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.services.retrieval_evaluator import (
    RetrievalEvaluationCase,
    evaluate_retrieval,
)


class RetrievalEvaluatorTest(unittest.TestCase):
    def test_explicit_source_identity_takes_precedence_over_parent(self):
        document = Document(page_content="evidence", metadata={"source_id": "precise-source", "parent_id": "parent"})
        metrics = evaluate_retrieval(lambda case: [document], [
            RetrievalEvaluationCase("question", ["precise-source"])
        ])
        self.assertEqual(metrics.recall_at_k, 1.0)

    def test_calculates_recall_hit_rate_and_mrr(self):
        cases = [
            RetrievalEvaluationCase("问题一", ["a", "b"]),
            RetrievalEvaluationCase("问题二", ["c"]),
        ]
        results = {
            "问题一": [self._document("x"), self._document("a")],
            "问题二": [self._document("y")],
        }

        metrics = evaluate_retrieval(lambda case: results[case.question], cases, top_k=2)

        self.assertEqual(metrics.case_count, 2)
        self.assertEqual(metrics.recall_at_k, 0.25)
        self.assertEqual(metrics.hit_rate_at_k, 0.5)
        self.assertEqual(metrics.mean_reciprocal_rank, 0.25)

    def test_empty_case_list_returns_zero_metrics(self):
        metrics = evaluate_retrieval(lambda case: [], [], top_k=5)

        self.assertEqual(metrics.case_count, 0)
        self.assertEqual(metrics.recall_at_k, 0.0)

    @staticmethod
    def _document(parent_id):
        return Document(page_content="内容", metadata={"parent_id": parent_id})


if __name__ == "__main__":
    unittest.main()
