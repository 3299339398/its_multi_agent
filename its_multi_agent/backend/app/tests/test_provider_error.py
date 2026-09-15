import sqlite3
import unittest

from its_multi_agent.backend.app.services.provider_error import (
    classify_agent_error,
    classify_provider_error,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class ProviderException(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.response = FakeResponse(status_code, message)


class ProviderErrorTest(unittest.TestCase):
    def test_unapproved_model_endpoint_has_actionable_message_without_retry(self):
        info = classify_agent_error(ValueError('Model base URL is not approved by the administrator'))
        self.assertIn('管理员', info.message)
        self.assertFalse(info.retryable)

    def test_attachment_error_preserves_actionable_message_without_retry(self):
        from its_multi_agent.backend.app.services.attachment_service import AttachmentError
        info = classify_agent_error(AttachmentError("Please select a vision model"))
        self.assertEqual(info.message, "Please select a vision model")
        self.assertFalse(info.retryable)

    def test_quota_error_is_clear_and_not_retried(self):
        info = classify_provider_error(ProviderException(403, "AllocationQuota.FreeTierOnly"))
        self.assertFalse(info.retryable)
        self.assertIn("额度已用完", info.message)

    def test_auth_error_is_clear_and_not_retried(self):
        info = classify_provider_error(ProviderException(401, "Unauthorized"))
        self.assertFalse(info.retryable)
        self.assertIn("鉴权失败", info.message)

    def test_payment_required_is_treated_as_quota_error(self):
        info = classify_provider_error(ProviderException(402, "payment required"))
        self.assertFalse(info.retryable)
        self.assertIn("额度已用完", info.message)

    def test_transient_errors_are_retried(self):
        for status_code in (408, 429, 500, 503):
            with self.subTest(status_code=status_code):
                self.assertTrue(
                    classify_provider_error(ProviderException(status_code, "temporary")).retryable
                )

    def test_bad_request_is_not_retried(self):
        info = classify_provider_error(ProviderException(400, "invalid request"))
        self.assertFalse(info.retryable)
        self.assertIn("配置", info.message)

    def test_storage_error_is_not_reported_as_model_failure(self):
        info = classify_agent_error(sqlite3.OperationalError("database is locked"))
        self.assertFalse(info.retryable)
        self.assertIn("会话存储", info.message)

    def test_unknown_programming_error_is_not_retried(self):
        info = classify_agent_error(RuntimeError("unexpected internal bug"))
        self.assertFalse(info.retryable)
        self.assertIn("系统处理", info.message)


if __name__ == "__main__":
    unittest.main()
