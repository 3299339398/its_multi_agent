import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.services.retrieval_service import RetrievalService


class FakeVectorStore:
    def __init__(self):
        self.search_queries = []

    def search_similarity_with_score(self, query, top_k, knowledge_space, domain):
        self.search_queries.append((query, knowledge_space, domain))
        shared = Document(
            page_content=f"匹配子块 {query}",
            metadata={
                "parent_id": "shared-parent",
                "parent_content": "知识空间:hr\n知识领域:policy\n报销制度正文",
                "title": "报销制度",
                "source_name": "报销制度.pdf",
            },
        )
        return [(shared, 0.9)]

    def embed_document(self, text):
        return [1.0, 0.0]

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeLexicalIndex:
    def __init__(self, documents=None):
        self.documents = documents or []
        self.search_calls = []

    def search(self, query, knowledge_space, domain, top_k):
        self.search_calls.append((query, knowledge_space, domain, top_k))
        return [Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                for doc in self.documents]


class FakeReranker:
    def rerank(self, question, documents, top_k):
        return documents[:top_k]


class RetrievalServiceTest(unittest.TestCase):
    def test_dedup_regression_retains_different_evidence_after_shared_prefix(self):
        prefix = "Shared introduction. " * 10
        documents = [Document(page_content=prefix + ending, metadata={"title": "Manual"})
                     for ending in ("ZX-81: reset", "ZX-82: replace")]
        service = RetrievalService.__new__(RetrievalService)
        self.assertEqual(len(service._deduplicate(documents + [documents[0]])), 2)

    def test_dedup_keeps_identical_content_from_distinct_documents_or_pages(self):
        documents = [Document(page_content="Same evidence", metadata={"title": "Manual", **meta})
                     for meta in ({"document_hash": "a", "page": 1},
                                  {"document_hash": "b", "page": 1},
                                  {"document_hash": "a", "page": 2})]
        service = RetrievalService.__new__(RetrievalService)
        self.assertEqual(len(service._deduplicate(documents)), 3)

    @patch("its_multi_agent.backend.knowledge.services.retrieval_service.settings.LEGACY_TITLE_RETRIEVAL_ENABLED", False)
    def test_multiple_queries_are_scoped_merged_and_deduplicated_by_parent(self):
        service = RetrievalService.__new__(RetrievalService)
        service.vector_store = FakeVectorStore()
        service.cross_encoder_reranker = FakeReranker()
        service.lexical_index = FakeLexicalIndex([
            Document(
                page_content="知识空间:hr\n知识领域:policy\n报销制度正文",
                metadata={
                    "parent_id": "shared-parent",
                    "title": "报销制度",
                    "source_name": "报销制度.pdf",
                    "bm25_rank": 1,
                },
            )
        ])
        service.spliter = None

        documents = service.retrieval(
            "钱怎么报", ["钱怎么报", "差旅报销流程"], "hr", "policy"
        )

        self.assertEqual(len(service.vector_store.search_queries), 2)
        self.assertTrue(all(query.startswith("知识空间:hr\n知识领域:policy\n")
                            for query, _, _ in service.vector_store.search_queries))
        self.assertTrue(all(scope == "hr" and domain == "policy"
                            for _, scope, domain in service.vector_store.search_queries))
        self.assertEqual(len(service.lexical_index.search_calls), 2)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["parent_id"], "shared-parent")
        self.assertEqual(documents[0].metadata["matched_query"], "钱怎么报")
        self.assertAlmostEqual(documents[0].metadata["rerank_score"], 0.9)
        self.assertEqual(documents[0].metadata["query_coverage_score"], 1.0)
        self.assertEqual(documents[0].metadata["rrf_score"], 1.0)

    @patch("its_multi_agent.backend.knowledge.services.retrieval_service.settings.RERANK_SCORE_THRESHOLD", 0.5)
    def test_irrelevant_candidates_are_removed_by_threshold(self):
        service = RetrievalService.__new__(RetrievalService)
        service.vector_store = FakeVectorStore()
        service.cross_encoder_reranker = FakeReranker()
        service.lexical_index = FakeLexicalIndex()
        candidate = Document(
            page_content="完全无关的内容",
            metadata={"matched_queries": [], "title": "其他资料"},
        )
        service.vector_store.embed_document = lambda text: [1.0, 0.0]
        service.vector_store.embed_documents = lambda texts: [[0.0, 1.0] for _ in texts]

        self.assertEqual(service._reranking([candidate], "差旅报销", query_count=1), [])

    def test_lexical_score_rewards_exact_identifiers(self):
        exact = RetrievalService._lexical_score(
            "设备出现 ERR-2048 怎么处理", "故障代码 ERR-2048 表示网络连接中断"
        )
        unrelated = RetrievalService._lexical_score(
            "设备出现 ERR-2048 怎么处理", "这是普通的设备维护说明"
        )

        self.assertGreater(exact, unrelated)

    def test_lexical_score_prefers_exact_identifier_over_partial_identifier(self):
        exact = RetrievalService._lexical_score("设备 ERR-2048 怎么处理", "故障代码 ERR-2048 表示网络中断")
        partial = RetrievalService._lexical_score("设备 ERR-2048 怎么处理", "故障代码 ERR-204 表示网络中断")

        self.assertGreater(exact, partial)

    def test_lexical_score_does_not_count_identifier_prefix_as_exact(self):
        exact = RetrievalService._lexical_score("错误码 ERR-204", "故障代码 ERR-204 表示网络中断")
        prefix = RetrievalService._lexical_score("错误码 ERR-204", "故障代码 ERR-2048 表示网络中断")

        self.assertGreater(exact, prefix)

    def test_rrf_rewards_results_found_by_both_channels(self):
        vector_only = Document(page_content="", metadata={"retrieval_ranks": [1]})
        both = Document(
            page_content="",
            metadata={"retrieval_ranks": [1], "bm25_ranks": [1]},
        )

        self.assertEqual(RetrievalService._rrf_score(vector_only), 0.5)
        self.assertEqual(RetrievalService._rrf_score(both), 1.0)

    def test_diversify_limits_same_document_and_keeps_other_sources(self):
        service = RetrievalService.__new__(RetrievalService)
        documents = [
            Document(page_content=f"chunk-{index}", metadata={
                "document_hash": "same", "rerank_score": 1.0 - index * .1,
            }) for index in range(3)
        ] + [Document(page_content="other", metadata={
            "document_hash": "other", "rerank_score": .5,
        })]

        selected = service._diversify(documents, limit=3, max_per_document=2)

        self.assertEqual([doc.page_content for doc in selected], ["chunk-0", "chunk-1", "other"])

    def test_reranking_reuses_exact_embedding_results(self):
        service = RetrievalService.__new__(RetrievalService)
        service.vector_store = FakeVectorStore()
        query_calls = []
        document_calls = []
        service.vector_store.embed_document = lambda text: query_calls.append(text) or [1.0, 0.0]
        service.vector_store.embed_documents = lambda texts: document_calls.append(list(texts)) or [
            [1.0, 0.0] for _ in texts
        ]
        candidate = Document(page_content="差旅报销正文", metadata={"title": "报销制度"})

        first = service._reranking([candidate], "差旅怎么报", query_count=1)
        second = service._reranking([candidate], "差旅怎么报", query_count=1)

        self.assertEqual(len(first), len(second))
        self.assertEqual(query_calls, ["差旅怎么报"])
        self.assertEqual(len(document_calls), 1)


if __name__ == "__main__":
    unittest.main()
