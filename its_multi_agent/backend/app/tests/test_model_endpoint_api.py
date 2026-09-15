import unittest
from unittest.mock import patch

from fastapi import HTTPException
from its_multi_agent.backend.app.api import routers
from its_multi_agent.backend.app.schemas.model_profile import ModelProfileCreate


class ModelEndpointApiTest(unittest.TestCase):
    def test_unapproved_endpoint_is_a_client_error_without_echoing_secrets(self):
        request = ModelProfileCreate(name='personal', model_name='model',
                                     base_url='http://127.0.0.1/v1', api_key='fake-test-secret')
        with patch.object(routers.user_model_profiles, 'save', side_effect=ValueError('not approved')):
            with self.assertRaises(HTTPException) as raised:
                routers.save_model_profile(request, {'user_id': 'alice'})
        self.assertEqual(raised.exception.status_code, 422)
        self.assertNotIn(request.api_key, raised.exception.detail)
