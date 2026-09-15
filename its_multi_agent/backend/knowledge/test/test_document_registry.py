import tempfile
import unittest
from pathlib import Path

from its_multi_agent.backend.knowledge.repositories.document_registry import DocumentRegistry


class DocumentRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry = DocumentRegistry(str(Path(self.temp_dir.name) / "registry.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_completed_document_cannot_be_claimed_again(self):
        self.assertTrue(self.registry.claim("hash-a", "a.md"))
        self.registry.complete("hash-a", 3)
        self.assertFalse(self.registry.claim("hash-a", "copy.md"))

    def test_failed_document_can_be_retried(self):
        self.assertTrue(self.registry.claim("hash-b", "b.md"))
        self.registry.fail("hash-b")
        self.assertTrue(self.registry.claim("hash-b", "b.md"))

    def test_lists_filters_and_summarizes_documents(self):
        self.registry.claim(
            "hash-a", "policy.md", content_hash="content-a",
            knowledge_space="hr", domain="policy", file_size=128,
            uploaded_by="admin",
        )
        self.registry.complete("hash-a", 4)
        self.registry.claim(
            "hash-b", "contract.pdf", knowledge_space="legal",
            domain="contract", file_size=256, uploaded_by="admin",
        )
        self.registry.fail("hash-b", "parse failed")

        result = self.registry.list_documents(search="policy", knowledge_space="hr")
        statistics = self.registry.statistics()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["uploaded_by"], "admin")
        self.assertEqual(result["items"][0]["file_size"], 128)
        self.assertEqual(statistics["total_documents"], 2)
        self.assertEqual(statistics["complete_documents"], 1)
        self.assertEqual(statistics["failed_documents"], 1)
        self.assertEqual(statistics["total_chunks"], 4)

    def test_soft_deleted_document_can_be_uploaded_again(self):
        self.registry.claim("hash-c", "guide.txt")
        self.registry.complete("hash-c", 2)
        self.registry.mark_deleted("hash-c", "admin")

        self.assertEqual(self.registry.list_documents()["total"], 0)
        deleted = self.registry.list_documents(include_deleted=True, status="deleted")
        self.assertEqual(deleted["items"][0]["deleted_by"], "admin")
        self.assertTrue(self.registry.claim("hash-c", "guide.txt"))
        self.assertEqual(self.registry.get_status("hash-c"), "processing")


if __name__ == "__main__":
    unittest.main()
