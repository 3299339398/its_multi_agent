import unittest
from unittest.mock import patch

from fastapi import HTTPException

from its_multi_agent.backend.knowledge.api.dependencies import verify_service_token
from its_multi_agent.backend.knowledge.config.settings import settings


class KnowledgeServiceAuthTest(unittest.TestCase):
    def test_accepts_matching_service_token(self):
        token = "service-token-that-is-at-least-32-characters"
        with patch.object(settings, "KNOWLEDGE_SERVICE_TOKEN", token):
            self.assertIsNone(verify_service_token(token))

    def test_rejects_missing_or_invalid_service_token(self):
        token = "service-token-that-is-at-least-32-characters"
        with patch.object(settings, "KNOWLEDGE_SERVICE_TOKEN", token):
            for supplied in (None, "wrong-token"):
                with self.subTest(supplied=supplied):
                    with self.assertRaises(HTTPException) as context:
                        verify_service_token(supplied)
                    self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
