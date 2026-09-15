import unittest

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.services.cross_encoder_reranker import (
    CrossEncoderReranker,
)


class FakeCrossEncoder:
    def predict(self, pairs):
        return [0.1 if "第一份" in content else 0.9 for _, content in pairs]


class CrossEncoderRerankerTest(unittest.TestCase):
    def test_disabled_reranker_preserves_fusion_order(self):
        documents = [self._document("a", "第一份"), self._document("b", "第二份")]

        result = CrossEncoderReranker(model_name="").rerank("问题", documents, 1)

        self.assertEqual(result[0].metadata["parent_id"], "a")

    def test_enabled_reranker_uses_pairwise_scores(self):
        documents = [self._document("a", "第一份"), self._document("b", "第二份")]
        reranker = CrossEncoderReranker(model_name="test", model=FakeCrossEncoder())

        result = reranker.rerank("问题", documents, 2)

        self.assertEqual([doc.metadata["parent_id"] for doc in result], ["b", "a"])
        self.assertEqual(result[0].metadata["cross_encoder_score"], 0.9)

    @staticmethod
    def _document(parent_id, content):
        return Document(page_content=content, metadata={"parent_id": parent_id})


if __name__ == "__main__":
    unittest.main()
