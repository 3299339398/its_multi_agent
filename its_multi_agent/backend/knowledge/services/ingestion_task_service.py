import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
from uuid import uuid4

from its_multi_agent.backend.knowledge.config.settings import settings
from its_multi_agent.backend.knowledge.repositories.document_registry import (
    DocumentBusyError, document_registry,
)


class IngestionTaskService:
    """Durable task state with a bounded in-process worker pool."""

    def __init__(self, processor, db_path: Optional[str] = None) -> None:
        self._processor = processor
        self._registry = document_registry
        self._db_path = Path(db_path or settings.INGESTION_TASK_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._upload_dir = Path(settings.INGESTION_UPLOAD_FOLDER_PATH)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max(1, settings.INGESTION_WORKERS))
        self._initialize()
        self._recover_pending_tasks()

    def create_task(
        self,
        *,
        document_hash: str,
        file_path: str,
        file_name: str,
        knowledge_space: str,
        domain: str,
        uploaded_by: str,
    ) -> Dict[str, Any]:
        task_id = uuid4().hex
        now = int(time.time())
        with self._registry.document_lock(document_hash, timeout=30), self._connect() as connection:
            document = self._registry.get_document(document_hash)
            if not document or document["status"] != "processing":
                raise ValueError("Document is not claimed for ingestion")
            connection.execute(
                """
                INSERT INTO ingestion_tasks(
                    task_id, document_hash, file_path, file_name, knowledge_space,
                    domain, uploaded_by, status, progress, message, error_message,
                    chunks_added, attempts, created_at, updated_at, document_generation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, '任务已排队', '', 0, 0, ?, ?, ?)
                """,
                (
                    task_id, document_hash, file_path, file_name,
                    knowledge_space, domain, uploaded_by, now, now, document["generation"],
                ),
            )
        self._submit(task_id)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_tasks(self, *, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM ingestion_tasks").fetchone()[0]
            rows = connection.execute(
                """
                SELECT * FROM ingestion_tasks
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": int(total), "page": page, "page_size": page_size}

    def retry_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if not task or task["status"] != "failed":
            return None
        if not Path(task["file_path"]).exists():
            return None
        try:
            with self._registry.document_lock(task["document_hash"]), self._connect_registry() as connection:
                current = connection.execute(
                    "SELECT status FROM ingestion_tasks WHERE task_id = ?", (task_id,),
                ).fetchone()
                if current["status"] != "failed":
                    return None
                updated = connection.execute(
                    """
                    UPDATE registry.documents SET status = 'processing', error_message = '', updated_at = ?
                    WHERE document_hash = ? AND generation = ? AND status = 'failed'
                    """,
                    (int(time.time()), task["document_hash"], task["document_generation"]),
                )
                if updated.rowcount != 1:
                    return None
                connection.execute(
                    """
                    UPDATE ingestion_tasks
                    SET status = 'queued', progress = 0, message = '任务已重新排队',
                        error_message = '', attempts = attempts + 1, updated_at = ?
                    WHERE task_id = ? AND status = 'failed'
                    """,
                    (int(time.time()), task_id),
                )
        except DocumentBusyError:
            return None
        self._submit(task_id)
        return self.get_task(task_id)

    def _submit(self, task_id: str) -> None:
        self._executor.submit(self._run, task_id)

    def _run(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if not task or task["status"] != "queued":
            return
        try:
            with self._registry.document_lock(task["document_hash"], timeout=30):
                with self._connect_registry() as connection:
                    claimed = connection.execute(
                        """
                        UPDATE ingestion_tasks SET status = 'processing', progress = 10,
                            message = '正在解析文档', updated_at = ?
                        WHERE task_id = ? AND status = 'queued' AND EXISTS (
                            SELECT 1 FROM registry.documents d
                            WHERE d.document_hash = ingestion_tasks.document_hash
                                AND d.generation = ingestion_tasks.document_generation
                                AND d.status = 'processing'
                        )
                        """,
                        (int(time.time()), task_id),
                    )
                    if claimed.rowcount != 1:
                        connection.execute(
                            """
                            UPDATE ingestion_tasks SET status = 'failed', progress = 100,
                                message = '文档状态已变更', error_message = '文档状态已变更', updated_at = ?
                            WHERE task_id = ? AND status = 'queued'
                            """,
                            (int(time.time()), task_id),
                        )
                        return
                self._ingest_claimed_task(task)
        except DocumentBusyError:
            return

    def _ingest_claimed_task(self, task: Dict[str, Any]) -> None:
        try:
            chunks_added = self._processor.ingest_file(
                task["file_path"],
                task["document_hash"],
                task["file_name"],
                task["knowledge_space"],
                task["domain"],
            )
            self._finish_task(task, "success", chunks_added=chunks_added)
        except Exception as error:
            try:
                self._finish_task(task, "failed", error_message=str(error))
            except Exception:
                pass
        else:
            try:
                Path(task["file_path"]).unlink(missing_ok=True)
            except OSError:
                pass

    def _finish_task(self, task, status, *, chunks_added=0, error_message="") -> None:
        with self._connect_registry() as connection:
            now = int(time.time())
            connection.execute(
                """
                UPDATE registry.documents SET status = ?, chunks_added = ?, error_message = ?, updated_at = ?
                WHERE document_hash = ? AND generation = ? AND status = 'processing'
                """,
                ("complete" if status == "success" else "failed", chunks_added, error_message[:1000],
                 now, task["document_hash"], task["document_generation"]),
            )
            connection.execute(
                """
                UPDATE ingestion_tasks SET status = ?, progress = 100, chunks_added = ?,
                    error_message = ?, message = ?, updated_at = ?
                WHERE task_id = ? AND status = 'processing'
                """,
                (status, chunks_added, error_message[:1000],
                 "文档入库完成" if status == "success" else "文档入库失败", now, task["task_id"]),
            )

    def delete_document(self, document_hash: str, actor: str) -> Dict[str, Any]:
        with self._registry.document_lock(document_hash):
            document = self._registry.get_document(document_hash)
            if not document or document["status"] == "deleted":
                raise LookupError("Document does not exist")
            if document["status"] == "processing":
                raise DocumentBusyError("Document is being processed")
            try:
                self._processor.vector_store.delete_document(
                    document_hash, document["knowledge_space"], document["domain"],
                )
                lexical_chunks = self._processor.lexical_index.delete_document(document_hash)
                self._registry.mark_deleted(document_hash, actor)
                return {
                    "status": "deleted", "document_hash": document_hash,
                    "lexical_chunks_deleted": lexical_chunks,
                }
            except Exception as error:
                self._registry.mark_deletion_failed(document_hash, str(error))
                raise

    def _update(
        self,
        task_id: str,
        status: str,
        progress: int,
        message: str,
        *,
        chunks_added: int = 0,
        error_message: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_tasks
                SET status = ?, progress = ?, message = ?, error_message = ?,
                    chunks_added = CASE WHEN ? > 0 THEN ? ELSE chunks_added END,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (status, progress, message, error_message[:1000], chunks_added, chunks_added, int(time.time()), task_id),
            )

    def _recover_pending_tasks(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_tasks WHERE status IN ('queued', 'processing')"
            ).fetchall()
        for row in rows:
            try:
                with self._registry.document_lock(row["document_hash"]):
                    current = self.get_task(row["task_id"])
                    if current["status"] not in {"queued", "processing"}:
                        continue
                    document = self._registry.get_document(row["document_hash"])
                    if (not document or document["status"] != "processing"
                            or document["generation"] != row["document_generation"]):
                        self._update(row["task_id"], "failed", 100, "文档状态已变更", error_message="文档状态已变更")
                        continue
                    if not Path(row["file_path"]).exists():
                        self._update(row["task_id"], "processing", 0, "任务文件不存在")
                        self._finish_task(dict(row), "failed", error_message="任务文件不存在")
                        continue
                    self._update(row["task_id"], "queued", 0, "服务恢复后重新排队")
                self._submit(row["task_id"])
            except DocumentBusyError:
                continue

    @contextmanager
    def _connect_registry(self) -> Iterator[sqlite3.Connection]:
        # Commit task and document state together while the caller holds the
        # document lock. This also makes retry crash-safe between the two DBs.
        with self._connect() as connection:
            connection.execute("ATTACH DATABASE ? AS registry", (str(self._registry._db_path),))
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_tasks (
                    task_id TEXT PRIMARY KEY,
                    document_hash TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    knowledge_space TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    uploaded_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    chunks_added INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_tasks_status ON ingestion_tasks(status)")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(ingestion_tasks)")}
            if "document_generation" not in columns:
                connection.execute("ALTER TABLE ingestion_tasks ADD COLUMN document_generation TEXT NOT NULL DEFAULT ''")


def create_ingestion_task_service(processor) -> IngestionTaskService:
    return IngestionTaskService(processor)
