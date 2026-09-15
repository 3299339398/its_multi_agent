import unittest
from unittest.mock import Mock

from its_multi_agent.backend.knowledge.services.ingestion.document_extractor import DocumentExtractor


class DocumentExtractorTest(unittest.TestCase):
    def tearDown(self):
        DocumentExtractor._ocr_engine = None

    def test_join_unique_text_avoids_duplicate_ocr(self):
        self.assertEqual(DocumentExtractor._join_unique_text("现有文字", "现有文字"), "现有文字")

    def test_recognize_image_combines_ocr_lines(self):
        engine = Mock(return_value=([
            ([[0, 0], [1, 0], [1, 1], [0, 1]], "第一行", 0.99),
            ([[0, 0], [1, 0], [1, 1], [0, 1]], "第二行", 0.98),
        ], None))
        DocumentExtractor._ocr_engine = engine

        from PIL import Image
        image = Image.new("RGB", (10, 10), "white")

        self.assertEqual(DocumentExtractor._recognize_image(image), "第一行\n第二行")
        engine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
