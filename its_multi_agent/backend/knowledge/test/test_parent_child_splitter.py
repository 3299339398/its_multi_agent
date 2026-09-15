import unittest

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.config.settings import settings
from its_multi_agent.backend.knowledge.services.ingestion.parent_child_splitter import ParentChildSplitter


class ParentChildSplitterTest(unittest.TestCase):
    def test_long_document_creates_searchable_children_with_parent_context(self):
        text = "\n\n".join(f"第 {index} 段 " + "技术说明" * 80 for index in range(12))
        source = Document(page_content=text, metadata={"page": 3, "title": "测试手册"})

        children = ParentChildSplitter().split([source], "测试手册.pdf", "hash-a")

        self.assertGreater(len(children), 1)
        self.assertTrue(all(child.metadata["chunk_type"] == "child" for child in children))
        self.assertTrue(all(child.metadata["page"] == 3 for child in children))
        self.assertTrue(all(len(child.metadata["parent_content"]) <= settings.PARENT_CHUNK_SIZE + 30
                            for child in children))
        self.assertTrue(all(len(child.page_content) <= settings.CHILD_CHUNK_SIZE + 30
                            for child in children))
        self.assertLess(len({child.metadata["parent_id"] for child in children}), len(children))

    def test_parent_ids_are_stable_and_distinguish_pages(self):
        splitter = ParentChildSplitter()
        documents = [
            Document(page_content="第一页", metadata={"page": 1}),
            Document(page_content="第二页", metadata={"page": 2}),
        ]

        first = splitter.split(documents, "手册.pdf", "hash-b")
        second = splitter.split(documents, "手册.pdf", "hash-b")

        self.assertEqual(
            [child.metadata["parent_id"] for child in first],
            [child.metadata["parent_id"] for child in second],
        )
        self.assertNotEqual(first[0].metadata["parent_id"], first[1].metadata["parent_id"])

    def test_custom_context_is_injected_into_parent_and_child(self):
        context = "知识空间:legal\n知识领域:contract\n文档来源:合同.docx"

        children = ParentChildSplitter().split(
            [Document(page_content="付款条件为验收后十个工作日。", metadata={"page": 2})],
            "合同.docx",
            "hash-contract",
            context_prefix=context,
        )

        self.assertEqual(len(children), 1)
        self.assertTrue(children[0].page_content.startswith(context))
        self.assertTrue(children[0].metadata["parent_content"].startswith(context))

    def test_heading_path_is_preserved_in_chunk_metadata_and_content(self):
        source = Document(page_content="处理步骤：断电后更换硬盘。", metadata={
            "title": "维修手册", "section_path": "电脑 > 存储 > 硬盘故障", "page": 4,
        })

        child = ParentChildSplitter().split([source], "维修手册.pdf", "hash-heading")[0]

        self.assertEqual(child.metadata["section_path"], "电脑 > 存储 > 硬盘故障")
        self.assertIn("章节路径:电脑 > 存储 > 硬盘故障", child.page_content)
        self.assertIn("章节路径:电脑 > 存储 > 硬盘故障", child.metadata["parent_content"])


if __name__ == "__main__":
    unittest.main()
