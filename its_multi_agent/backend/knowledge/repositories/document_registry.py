import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from uuid import uuid4

from its_multi_agent.backend.knowledge.config.settings import settings


class DocumentBusyError(ValueError):
    """Another process is mutating this document's indexes."""


class DocumentRegistry:
    """Tracks uploaded document hashes so ingestion is idempotent."""

    CLAIM_TTL_SECONDS = 3600

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = Path(db_path or settings.DOCUMENT_REGISTRY_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def claim(
        self,
        document_hash: str,
        file_name: str,
        *,
        content_hash: str = "",
        knowledge_space: str = "default",
        domain: str = "general",
        file_size: int = 0,
        uploaded_by: str = "system",
    ) -> bool:
        try:
            with self.document_lock(document_hash):
                return self._claim(
                    document_hash, file_name, content_hash=content_hash,
                    knowledge_space=knowledge_space, domain=domain,
                    file_size=file_size, uploaded_by=uploaded_by,
                )
        except DocumentBusyError:
            return False

    def _claim(
        self, document_hash, file_name, *, content_hash, knowledge_space,
        domain, file_size, uploaded_by,
    ) -> bool:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, updated_at FROM documents WHERE document_hash = ?",
                (document_hash,),
            ).fetchone()
            if row and row["status"] == "complete":
                return False
            if row and row["status"] == "processing" and now - row["updated_at"] < self.CLAIM_TTL_SECONDS:
                return False

            connection.execute(
                """
                INSERT INTO documents(
                    document_hash, content_hash, file_name, status, chunks_added,
                    knowledge_space, domain, file_size, uploaded_by,
                    error_message, created_at, updated_at, deleted_at, deleted_by, generation
                )
                VALUES (?, ?, ?, 'processing', 0, ?, ?, ?, ?, '', ?, ?, NULL, '', ?)
                ON CONFLICT(document_hash) DO UPDATE SET
                    file_name = excluded.file_name,
                    content_hash = excluded.content_hash,
                    status = 'processing',
                    chunks_added = 0,
                    knowledge_space = excluded.knowledge_space,
                    domain = excluded.domain,
                    file_size = excluded.file_size,
                    uploaded_by = excluded.uploaded_by,
                    error_message = '',
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    deleted_at = NULL,
                    deleted_by = '',
                    generation = excluded.generation
                """,
                (
                    document_hash, content_hash, file_name, knowledge_space,
                    domain, file_size, uploaded_by, now, now, uuid4().hex,
                ),
            )
            return True

    def complete(self, document_hash: str, chunks_added: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'complete', chunks_added = ?, updated_at = ?
                WHERE document_hash = ? AND status = 'processing'
                """,
                (chunks_added, int(time.time()), document_hash),
            )

    def get_status(self, document_hash: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM documents WHERE document_hash = ?",
                (document_hash,),
            ).fetchone()
        return str(row["status"]) if row else None

    def fail(self, document_hash: str, error_message: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'failed', error_message = ?, updated_at = ?
                WHERE document_hash = ? AND status = 'processing'
                """,
                (error_message[:1000], int(time.time()), document_hash),
            )

    def get_document(self, document_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_hash = ?",
                (document_hash,),
            ).fetchone()
        return dict(row) if row else None

    def list_documents(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        status: str = "",
        knowledge_space: str = "",
        domain: str = "",
        include_deleted: bool = False,
    ) -> Dict[str, Any]:
        conditions = []
        parameters: List[Any] = []
        if not include_deleted:
            conditions.append("status != 'deleted'")
        if search:
            conditions.append("file_name LIKE ?")
            parameters.append(f"%{search}%")
        if status:
            conditions.append("status = ?")
            parameters.append(status)
        if knowledge_space:
            conditions.append("knowledge_space = ?")
            parameters.append(knowledge_space)
        if domain:
            conditions.append("domain = ?")
            parameters.append(domain)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM documents {where_clause}", parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM documents {where_clause}
                ORDER BY updated_at DESC, file_name ASC
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, offset],
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def statistics(self) -> Dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_documents,
                    SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS complete_documents,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing_documents,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_documents,
                    SUM(CASE WHEN status = 'complete' THEN chunks_added ELSE 0 END) AS total_chunks,
                    COUNT(DISTINCT knowledge_space) AS knowledge_spaces,
                    COUNT(DISTINCT domain) AS domains
                FROM documents
                WHERE status != 'deleted'
                """
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def mark_deleted(self, document_hash: str, deleted_by: str) -> None:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'deleted', chunks_added = 0, error_message = '',
                    deleted_at = ?, deleted_by = ?, updated_at = ?
                WHERE document_hash = ?
                """,
                (now, deleted_by, now, document_hash),
            )

    def mark_deletion_failed(self, document_hash: str, error_message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = 'deletion_failed', error_message = ?, updated_at = ?
                WHERE document_hash = ?
                """,
                (error_message[:1000], int(time.time()), document_hash),
            )

    @contextmanager
    def document_lock(self, document_hash: str, *, timeout: float = 0) -> Iterator[None]:
        # A separate SQLite lock per document avoids holding the registry's
        # global write lock during external index IO. Process death releases it.
        lock_dir = self._db_path.with_suffix(self._db_path.suffix + ".locks")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_name = hashlib.sha256(document_hash.encode("utf-8")).hexdigest()
        connection = sqlite3.connect(lock_dir / f"{lock_name}.db", timeout=timeout)
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower():
                    raise
                raise DocumentBusyError("Document is being processed") from error
            yield
        finally:
            connection.rollback()
            connection.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, timeout=10)
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
                CREATE TABLE IF NOT EXISTS documents (
                    document_hash TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chunks_added INTEGER NOT NULL DEFAULT 0,
                    knowledge_space TEXT NOT NULL DEFAULT 'default',
                    domain TEXT NOT NULL DEFAULT 'general',
                    file_size INTEGER NOT NULL DEFAULT 0,
                    uploaded_by TEXT NOT NULL DEFAULT 'system',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    deleted_at INTEGER,
                    deleted_by TEXT NOT NULL DEFAULT ''
                )
                """
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(documents)")
            }
            migrations = {
                "generation": "TEXT NOT NULL DEFAULT ''",
                "content_hash": "TEXT NOT NULL DEFAULT ''",
                "knowledge_space": "TEXT NOT NULL DEFAULT 'default'",
                "domain": "TEXT NOT NULL DEFAULT 'general'",
                "file_size": "INTEGER NOT NULL DEFAULT 0",
                "uploaded_by": "TEXT NOT NULL DEFAULT 'system'",
                "error_message": "TEXT NOT NULL DEFAULT ''",
                "created_at": "INTEGER NOT NULL DEFAULT 0",
                "deleted_at": "INTEGER",
                "deleted_by": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE documents ADD COLUMN {column} {definition}"
                    )
            connection.execute(
                "UPDATE documents SET created_at = updated_at WHERE created_at = 0"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(knowledge_space, domain)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
            )


document_registry = DocumentRegistry()
