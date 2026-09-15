import multiprocessing
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.knowledge.repositories.document_registry import DocumentRegistry
from its_multi_agent.backend.knowledge.services.ingestion_task_service import IngestionTaskService


class ManualTaskService(IngestionTaskService):
    def _submit(self, task_id):
        pass


class FakeIndex:
    def __init__(self):
        self.documents = set()

    def delete_document(self, document_hash, *scope):
        self.documents.discard(document_hash)
        return 1


class FakeProcessor:
    def __init__(self):
        self.vector_store = FakeIndex()
        self.lexical_index = FakeIndex()
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def ingest_file(self, file_path, document_hash, *metadata):
        self.calls += 1
        self.started.set()
        if not self.release.wait(10):
            raise RuntimeError("test worker timed out")
        self.vector_store.documents.add(document_hash)
        self.lexical_index.documents.add(document_hash)
        return 1


def hold_document_lock(registry_path, document_hash, started, release):
    registry = DocumentRegistry(registry_path)
    with registry.document_lock(document_hash):
        started.set()
        release.wait(10)


class IngestionTaskServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = DocumentRegistry(str(self.root / "registry.db"))
        registry_patch = patch(
            "its_multi_agent.backend.knowledge.services.ingestion_task_service.document_registry",
            self.registry,
        )
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        self.processor = FakeProcessor()
        self.services = []
        self.service = self.make_service()

    def tearDown(self):
        self.processor.release.set()
        for service in self.services:
            service._executor.shutdown(wait=True)
        self.temp.cleanup()

    def make_service(self):
        service = ManualTaskService(
            self.processor, str(self.root / "tasks.db"),
        )
        self.services.append(service)
        return service

    def create_task(self, document_hash="hash-a"):
        path = self.root / f"{document_hash}.md"
        path.write_text("content", encoding="utf-8")
        self.assertTrue(self.registry.claim(document_hash, path.name))
        return self.service.create_task(
            document_hash=document_hash, file_path=str(path), file_name=path.name,
            knowledge_space="default", domain="general", uploaded_by="admin",
        )["task_id"]

    def fail_task(self, task_id):
        self.registry.fail(self.service.get_task(task_id)["document_hash"], "parse failed")
        self.service._update(task_id, "failed", 100, "parse failed")

    def test_retry_marks_document_processing_and_blocks_delete_before_worker(self):
        task_id = self.create_task()
        self.fail_task(task_id)
        self.assertIsNotNone(self.service.retry_task(task_id))
        self.assertEqual(self.registry.get_status("hash-a"), "processing")
        with self.assertRaises(ValueError):
            self.service.delete_document("hash-a", "admin")
        self.service._run(task_id)
        self.assertEqual(self.registry.get_status("hash-a"), "complete")

    def test_deleted_document_rejects_retry_and_stale_worker_without_index_writes(self):
        task_id = self.create_task()
        self.fail_task(task_id)
        self.service.delete_document("hash-a", "admin")
        self.assertIsNone(self.service.retry_task(task_id))
        self.service._update(task_id, "queued", 0, "stale queued task")
        self.service._run(task_id)
        self.assertEqual(self.processor.calls, 0)
        self.assertEqual(self.processor.vector_store.documents, set())
        self.assertEqual(self.processor.lexical_index.documents, set())
        self.assertEqual(self.registry.get_status("hash-a"), "deleted")
        self.assertEqual(self.service.get_task(task_id)["status"], "failed")

    def test_delete_in_progress_rejects_retry_and_reupload(self):
        task_id = self.create_task()
        self.fail_task(task_id)
        started, release = threading.Event(), threading.Event()
        original_delete = self.processor.vector_store.delete_document

        def delete(document_hash, *scope):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test deletion timed out")
            return original_delete(document_hash, *scope)

        with patch.object(self.processor.vector_store, "delete_document", delete):
            with ThreadPoolExecutor(max_workers=1) as executor:
                deletion = executor.submit(self.service.delete_document, "hash-a", "admin")
                self.assertTrue(started.wait(5))
                try:
                    self.assertIsNone(self.service.retry_task(task_id))
                    self.assertFalse(self.registry.claim("hash-a", "copy.md"))
                finally:
                    release.set()
                deletion.result(timeout=5)
        self.assertEqual(self.registry.get_status("hash-a"), "deleted")
        self.assertEqual(self.processor.calls, 0)

    def test_failed_task_claim_never_writes_indexes(self):
        task_id = self.create_task()
        with patch.object(self.service, "_connect_registry", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                self.service._run(task_id)
        self.assertEqual(self.processor.calls, 0)
        self.assertEqual(self.service.get_task(task_id)["status"], "queued")

    def test_task_creation_waits_for_an_inflight_duplicate_upload_check(self):
        self.registry.claim("hash-a", "a.md")
        entered = threading.Event()

        def create():
            entered.set()
            return self.service.create_task(
                document_hash="hash-a", file_path=str(self.root / "a.md"),
                file_name="a.md", knowledge_space="default", domain="general", uploaded_by="admin",
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.registry.document_lock("hash-a"):
                future = executor.submit(create)
                self.assertTrue(entered.wait(5))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=0.1)
            self.assertEqual(future.result(timeout=5)["status"], "queued")

    def test_existing_databases_migrate_and_recover_pending_task(self):
        task_id = self.create_task()
        with sqlite3.connect(self.root / "registry.db") as connection:
            connection.execute("ALTER TABLE documents DROP COLUMN generation")
        connection.close()
        with sqlite3.connect(self.root / "tasks.db") as connection:
            connection.execute("ALTER TABLE ingestion_tasks DROP COLUMN document_generation")
        connection.close()
        DocumentRegistry(str(self.root / "registry.db"))
        other = self.make_service()
        other._run(task_id)
        self.assertEqual(self.registry.get_status("hash-a"), "complete")
        self.assertEqual(other.get_task(task_id)["status"], "success")

    def test_recovery_of_missing_file_fails_document_and_task_together(self):
        task_id = self.create_task()
        Path(self.service.get_task(task_id)["file_path"]).unlink()
        self.make_service()
        self.assertEqual(self.registry.get_status("hash-a"), "failed")
        self.assertEqual(self.service.get_task(task_id)["status"], "failed")

    def test_partial_deletion_failure_can_only_be_retried_as_deletion(self):
        task_id = self.create_task()
        self.fail_task(task_id)
        self.processor.vector_store.documents.add("hash-a")
        self.processor.lexical_index.documents.add("hash-a")
        with patch.object(self.processor.lexical_index, "delete_document", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                self.service.delete_document("hash-a", "admin")
        self.assertEqual(self.registry.get_status("hash-a"), "deletion_failed")
        self.assertIsNone(self.service.retry_task(task_id))
        self.service.delete_document("hash-a", "admin")
        self.assertEqual(self.registry.get_status("hash-a"), "deleted")
        self.assertEqual(self.processor.vector_store.documents, set())
        self.assertEqual(self.processor.lexical_index.documents, set())

    def test_concurrent_retry_is_accepted_once_across_service_instances(self):
        task_id = self.create_task()
        self.fail_task(task_id)
        other = self.make_service()
        barrier = threading.Barrier(2)

        def retry(service):
            barrier.wait()
            return service.retry_task(task_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(retry, [self.service, other]))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.service.get_task(task_id)["attempts"], 1)

    def test_duplicate_workers_and_recovery_do_not_repeat_active_index_writes(self):
        task_id = self.create_task()
        self.processor.release.clear()
        with ThreadPoolExecutor(max_workers=2) as executor:
            worker = executor.submit(self.service._run, task_id)
            self.assertTrue(self.processor.started.wait(5))
            try:
                other = self.make_service()
                self.assertEqual(other.get_task(task_id)["status"], "processing")
                other._run(task_id)
                with self.assertRaises(ValueError):
                    other.delete_document("hash-a", "admin")
            finally:
                self.processor.release.set()
            worker.result(timeout=5)
        self.service._run(task_id)
        self.assertEqual(self.processor.calls, 1)
        self.service.delete_document("hash-a", "admin")
        self.assertEqual(self.processor.vector_store.documents, set())
        self.assertEqual(self.processor.lexical_index.documents, set())

    def test_recovery_respects_document_lock_held_in_another_process(self):
        task_id = self.create_task()
        self.service._update(task_id, "processing", 10, "working")
        context = multiprocessing.get_context("spawn")
        started, release = context.Event(), context.Event()
        process = context.Process(
            target=hold_document_lock,
            args=(str(self.root / "registry.db"), "hash-a", started, release),
        )
        process.start()
        try:
            self.assertTrue(started.wait(5))
            self.make_service()
            self.assertEqual(self.service.get_task(task_id)["status"], "processing")
            process.terminate()
            process.join(10)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(10)
        self.assertNotEqual(process.exitcode, 0)
        self.make_service()
        self.assertEqual(self.service.get_task(task_id)["status"], "queued")
        self.service._run(task_id)
        self.assertEqual(self.processor.calls, 1)

    def test_old_failed_task_cannot_retry_after_same_document_is_uploaded_again(self):
        old_task = self.create_task()
        self.fail_task(old_task)
        new_task = self.create_task()
        self.fail_task(new_task)
        self.assertIsNone(self.service.retry_task(old_task))
        self.assertIsNotNone(self.service.retry_task(new_task))
        self.service._run(old_task)
        self.assertEqual(self.processor.calls, 0)
        self.service._run(new_task)
        self.assertEqual(self.processor.calls, 1)

    def test_deleted_registry_cannot_be_completed_or_failed_by_stale_updates(self):
        self.create_task()
        self.registry.mark_deleted("hash-a", "admin")
        self.registry.complete("hash-a", 4)
        self.registry.fail("hash-a", "stale failure")
        self.assertEqual(self.registry.get_status("hash-a"), "deleted")


if __name__ == "__main__":
    unittest.main()
