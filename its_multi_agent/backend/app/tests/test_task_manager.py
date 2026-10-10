import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.app.repositories.sqlite_task_repository import SQLiteTaskRepository
from its_multi_agent.backend.app.services.task_manager import TaskManager
from its_multi_agent.backend.app.schemas.request import ChatMessageRequest, UserContext, TemporaryModelRequest


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repository = SQLiteTaskRepository(str(Path(self.temp.name) / "tasks.db"))

    @staticmethod
    def finish(reason="NORMAL", error=None):
        return "data: " + json.dumps({
            "status": "FINISHED",
            "metadata": {"finishReason": reason, "errorMessage": error},
        }) + "\n\n"

    def test_run_survives_subscriber_disconnect_and_events_replay(self):
        async def scenario():
            manager = TaskManager(self.repository)

            async def fake_process(*args, **kwargs):
                yield "data: first\n\n"
                await asyncio.sleep(0)
                yield "data: last\n\n"
                yield self.finish()

            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task", fake_process):
                run_id = await manager.start(ChatMessageRequest(query="hello", context=UserContext(session_id="s1")), "u1")
                stream = manager.subscribe(run_id, "u1")
                self.assertEqual(await stream.__anext__(), "data: first\n\n")
                await stream.aclose()
                await asyncio.sleep(0.05)
                self.assertEqual(manager.get(run_id, "u1")["status"], "completed")
                replay = manager.subscribe(run_id, "u1")
                self.assertEqual(await replay.__anext__(), "data: first\n\n")
                self.assertEqual(await replay.__anext__(), "data: last\n\n")
                self.assertEqual(await replay.__anext__(), self.finish())
                await replay.aclose()

        asyncio.run(scenario())

    def test_tasks_are_isolated_by_user(self):
        manager = TaskManager(self.repository)
        self.assertIsNone(manager.get("missing", "other"))
        self.assertEqual(manager.list_for_session("s", "other"), [])

    def test_error_finish_sets_failed_status(self):
        async def scenario():
            manager = TaskManager(self.repository)

            async def fake_process(*args, **kwargs):
                yield self.finish("ERROR", "provider unavailable")

            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task", fake_process):
                run_id = await manager.start(ChatMessageRequest(query="hello", context=UserContext(session_id="s1")), "u1")
                await asyncio.sleep(0.05)
                result = manager.get(run_id, "u1")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["finish_reason"], "ERROR")
                self.assertEqual(result["error"], "provider unavailable")

        asyncio.run(scenario())

    def test_missing_finish_sets_failed_status(self):
        async def scenario():
            manager = TaskManager(self.repository)

            async def fake_process(*args, **kwargs):
                yield "data: partial\n\n"

            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task", fake_process):
                run_id = await manager.start(ChatMessageRequest(query="hello", context=UserContext(session_id="s1")), "u1")
                await asyncio.sleep(0.05)
                self.assertEqual(manager.get(run_id, "u1")["status"], "failed")

        asyncio.run(scenario())

    def test_get_loads_a_persisted_task_after_process_restart(self):
        request = ChatMessageRequest(query="hello", context=UserContext(session_id="s1"))
        self.repository.create("persisted", "u1", "s1", request, 1.0)
        self.repository.update("persisted", "completed")

        result = TaskManager(self.repository).get("persisted", "u1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["session_id"], "s1")
        self.assertIsNone(TaskManager(self.repository).get("persisted", "u2"))

    def test_temporary_model_credentials_are_not_persisted(self):
        request = ChatMessageRequest(
            query="hello", context=UserContext(session_id="s1"),
            temporary_model=TemporaryModelRequest(
                name="temp", model_name="model", base_url="https://example.test/v1",
                api_key="super-secret-key",
            ),
        )
        self.repository.create("secret-task", "u1", "s1", request, 1.0)
        with self.repository._connect() as db:
            stored = db.execute("SELECT request_json FROM agent_tasks WHERE run_id='secret-task'").fetchone()[0]
        self.assertNotIn("super-secret-key", stored)
        self.assertIn("_resume_blocked", stored)

    def test_processing_tasks_are_not_replayed_after_restart(self):
        request = ChatMessageRequest(query="hello", context=UserContext(session_id="s1"))
        self.repository.create("interrupted", "u1", "s1", request, 1.0)
        self.repository.update("interrupted", "running")

        async def scenario():
            manager = TaskManager(self.repository)
            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task") as process:
                await manager.resume_pending()
                await asyncio.sleep(0)
                process.assert_not_called()
            self.assertEqual(manager.get("interrupted", "u1")["status"], "failed")

        asyncio.run(scenario())

    def test_other_manager_subscribes_to_live_persisted_events(self):
        async def scenario():
            producer, subscriber = TaskManager(self.repository), TaskManager(self.repository)
            release = asyncio.Event()
            async def fake_process(*args, **kwargs):
                yield "data: first\n\n"
                await release.wait()
                yield self.finish()
            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task", fake_process):
                run_id = await producer.start(ChatMessageRequest(query="hello", context=UserContext(session_id="s")), "u")
                stream = subscriber.subscribe(run_id, "u")
                self.assertEqual(await asyncio.wait_for(anext(stream), 2), "data: first\n\n")
                release.set()
                self.assertEqual(await asyncio.wait_for(anext(stream), 2), self.finish())
                await producer._tasks[run_id].task
                self.assertEqual(subscriber.get(run_id, "u")["status"], "completed")
                await stream.aclose()
        asyncio.run(scenario())

    def test_remote_cancel_is_seen_by_lease_heartbeat(self):
        async def scenario():
            producer, controller = TaskManager(self.repository), TaskManager(self.repository)
            producer._lease_seconds = 0.3
            entered = asyncio.Event()
            async def fake_process(*args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
                yield self.finish()
            with patch("its_multi_agent.backend.app.services.task_manager.MultiAgentService.process_task", fake_process):
                run_id = await producer.start(ChatMessageRequest(query="hello", context=UserContext(session_id="s")), "u")
                await entered.wait()
                self.assertTrue(await controller.cancel(run_id, "u"))
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(producer._tasks[run_id].task, 2)
                self.assertEqual(controller.get(run_id, "u")["status"], "cancelled")
                packets = [packet async for packet in controller.subscribe(run_id, "u")]
                self.assertEqual(json.loads(packets[-1].removeprefix("data: "))["status"], "FINISHED")
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
