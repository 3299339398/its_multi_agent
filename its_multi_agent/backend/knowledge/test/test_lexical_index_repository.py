import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.repositories.lexical_index_repository import (
    LexicalIndexRepository,
)


class LexicalIndexRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = LexicalIndexRepository(
            str(Path(self.temp_dir.name) / "lexical.db")
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bm25_search_is_independent_and_scope_filtered(self):
        self.repository.replace_document(
            "hash-hr",
            [self._child("hr-parent", "设备出现 ERR-2048 时需要重置网络。")],
            "hr",
            "policy",
        )
        self.repository.replace_document(
            "hash-other",
            [self._child("other-parent", "ERR-2048 是合同模板编号。")],
            "legal",
            "contract",
        )

        results = self.repository.search("ERR-2048 怎么处理", "hr", "policy", 5)

        self.assertEqual([doc.metadata["parent_id"] for doc in results], ["hr-parent"])
        self.assertEqual(results[0].metadata["retrieval_channel"], "bm25")
        self.assertEqual(results[0].metadata["bm25_rank"], 1)

    def test_replacing_a_document_removes_stale_parent_rows(self):
        self.repository.replace_document(
            "hash-a",
            [self._child("old-parent", "旧版差旅报销规则")],
            "default",
            "general",
        )
        self.repository.replace_document(
            "hash-a",
            [self._child("new-parent", "新版采购审批规则")],
            "default",
            "general",
        )

        self.assertEqual(self.repository.search("差旅报销", top_k=5), [])
        self.assertEqual(
            [doc.metadata["parent_id"] for doc in self.repository.search("采购审批", top_k=5)],
            ["new-parent"],
        )

    @staticmethod
    def _child(parent_id, parent_content):
        return Document(
            page_content="用于向量化的子块",
            metadata={
                "parent_id": parent_id,
                "parent_content": parent_content,
                "title": "测试资料",
                "source_name": "测试资料.pdf",
            },
        )


if __name__ == "__main__":
    unittest.main()
