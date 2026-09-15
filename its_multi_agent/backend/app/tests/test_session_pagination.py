import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.app.repositories.sqlite_session_repository import SQLiteSessionRepository


class SessionPaginationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.object(SQLiteSessionRepository, '_migrate_legacy_json'):
            self.repo = SQLiteSessionRepository(str(Path(self.temp.name) / 'sessions.db'))
        for index in range(7):
            self.repo.append_message('alice', 's', {'role': 'user', 'content': f'Question {index}'})
            self.repo.append_message('alice', 's', {'role': 'assistant', 'content': f'Answer {index}',
                                                 'sources': [{'source_id': f'src-{index}', 'excerpt': 'evidence' * 1000}]})
        self.repo.append_message('bob', 's', {'role': 'user', 'content': 'Private Bob'})

    def test_list_returns_bounded_metadata_without_archives(self):
        self.repo.append_message('alice', 'other', {'role': 'user', 'content': 'Another'})
        with patch.object(self.repo, 'load_session', side_effect=AssertionError('must not load archives')):
            first = self.repo.list_sessions('alice', page=1, page_size=1)
            second = self.repo.list_sessions('alice', page=2, page_size=1)
        self.assertEqual(first['total_sessions'], 2)
        self.assertEqual(first['next_page'], 2)
        self.assertIsNone(second['next_page'])
        rows = first['sessions'] + second['sessions']
        self.assertEqual({row['session_id'] for row in rows}, {'s', 'other'})
        session = next(row for row in rows if row['session_id'] == 's')
        self.assertEqual(session['title'], 'Question 0')
        self.assertEqual(session['total_messages'], 14)
        self.assertNotIn('memory', session)
        self.assertNotIn('evidence', str(rows))
        self.assertNotIn('Private Bob', str(rows))

    def test_message_cursor_keeps_snapshots_and_is_stable_after_new_messages(self):
        first = self.repo.load_message_page('alice', 's', page_size=4)
        self.assertEqual(first['messages'][-1]['content'], 'Answer 6')
        self.assertEqual(first['messages'][-1]['sources'][0]['source_id'], 'src-6')
        self.repo.append_message('alice', 's', {'role': 'user', 'content': 'New message'})
        second = self.repo.load_message_page('alice', 's', page_size=4, before_id=first['next_before_id'])
        self.assertEqual(second['messages'][-1]['content'], 'Answer 4')
        self.assertTrue(set(m['id'] for m in first['messages']).isdisjoint(m['id'] for m in second['messages']))
        self.assertIsNone(self.repo.load_message_page('bob', 'other'))
        bob = self.repo.load_message_page('bob', 's')
        self.assertEqual(len(bob['messages']), 1)
        self.assertIsNone(bob['next_before_id'])

    def test_api_uses_authenticated_owner_and_returns_404_for_missing_session(self):
        from fastapi import HTTPException
        from its_multi_agent.backend.app.api import routers
        with patch.object(routers.session_service, '_repo', self.repo):
            result = routers.get_session_messages('s', page_size=3, before_id=None,
                                                  workspace_id='default', user={'user_id': 'bob'})
            self.assertEqual(result['messages'][0]['content'], 'Private Bob')
            with self.assertRaises(HTTPException) as raised:
                routers.get_session_messages('other', page_size=3, before_id=None,
                                             workspace_id='default', user={'user_id': 'bob'})
            self.assertEqual(raised.exception.status_code, 404)

    def test_delete_session_is_owner_scoped_and_cascades_messages(self):
        self.assertTrue(self.repo.delete_session('alice', 's'))
        self.assertIsNone(self.repo.load_session('alice', 's'))
        self.assertIsNotNone(self.repo.load_session('bob', 's'))
        self.assertFalse(self.repo.delete_session('alice', 'missing'))

    def test_delete_session_api_invalidates_cache_and_returns_404_when_missing(self):
        from fastapi import HTTPException
        from its_multi_agent.backend.app.api import routers

        with patch.object(routers.session_service, '_repo', self.repo), \
             patch.object(routers.session_service, '_cache') as cache:
            result = routers.delete_user_session('s', workspace_id='default', user={'user_id': 'alice'})
            self.assertEqual(result['session_id'], 's')
            cache.invalidate.assert_called_once_with('alice', 's')
            with self.assertRaises(HTTPException) as raised:
                routers.delete_user_session('s', workspace_id='default', user={'user_id': 'alice'})
            self.assertEqual(raised.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
