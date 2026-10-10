import tempfile
import unittest
from pathlib import Path

from its_multi_agent.backend.app.repositories.sqlite_task_repository import SQLiteTaskRepository, execution_lease, TaskLeaseLost


class TaskLeaseTest(unittest.TestCase):
    def test_only_one_owner_can_claim_a_task(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteTaskRepository(str(Path(folder) / "tasks.db"))
            repository.create("run-1", "user-1", "session-1", {"query": "x"}, 1.0)
            self.assertTrue(repository.claim("run-1", "worker-a", lease_seconds=60))
            self.assertFalse(repository.claim("run-1", "worker-b", lease_seconds=60))
            self.assertTrue(repository.renew_lease("run-1", "worker-a", lease_seconds=60))
            repository.release_lease("run-1", "worker-a")
            self.assertTrue(repository.claim("run-1", "worker-b", lease_seconds=60))

    def test_stale_owner_cannot_commit_status_event_or_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteTaskRepository(str(Path(folder) / "tasks.db"))
            repository.create("run", "user", "session", {}, 1)
            self.assertTrue(repository.claim("run", "old"))
            with repository._connect() as db:
                db.execute("UPDATE agent_tasks SET lease_expires_at=0 WHERE run_id='run'")
            self.assertFalse(repository.renew_lease("run", "old"))
            self.assertTrue(repository.claim("run", "new"))
            token = execution_lease.set(("run", "old"))
            try:
                for operation in (
                    lambda: repository.update("run", "failed"),
                    lambda: repository.append_event("run", "stale"),
                    lambda: repository.save_checkpoint("run", {"stale": True}),
                    lambda: repository.save_execution_checkpoint("run", {"stale": True}),
                ):
                    with self.assertRaises(TaskLeaseLost):
                        operation()
            finally:
                execution_lease.reset(token)
            self.assertEqual(repository.get("run", "user")["lease_owner"], "new")
            self.assertEqual(repository.events("run"), [])

    def test_resume_preserves_audit_but_replays_only_current_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteTaskRepository(str(Path(folder) / "tasks.db"))
            repository.create("run", "user", "session", {}, 1)
            repository.append_event("run", "old FINISHED")
            repository.update("run", "failed")
            self.assertTrue(repository.queue_resume("run", "user"))
            self.assertFalse(repository.queue_resume("run", "user"))
            repository.append_event("run", "new attempt")
            self.assertEqual(repository.events("run"), ["new attempt"])
            with repository._connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM agent_task_events").fetchone()[0], 2)

    def test_startup_does_not_fail_live_running_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = SQLiteTaskRepository(str(Path(folder) / "tasks.db"))
            repository.create("run", "user", "session", {}, 1)
            repository.claim("run", "live")
            repository.update("run", "running")
            self.assertFalse(repository.fail_expired("run", "restart"))
            self.assertEqual(repository.get("run", "user")["status"], "running")


if __name__ == "__main__":
    unittest.main()
