import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from its_multi_agent.backend.app.config.settings import settings


class SQLiteMemoryRepository:
    """提供轻量文本检索的本地长期记忆存储。"""

    supports_vectors = False

    def __init__(self, db_path: Optional[str] = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "memories.db"
        self._db_path = Path(db_path or settings.MEMORY_SQLITE_PATH or default_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def available(self) -> bool:
        return True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance REAL NOT NULL,
                    source_session_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    UNIQUE(user_id, normalized_content)
                );
                CREATE INDEX IF NOT EXISTS idx_memories_user_expiry
                    ON memories(user_id, expires_at, importance DESC, created_at DESC);
                """
            )

    def upsert_or_insert(self, memory: Dict[str, Any], threshold=None) -> str:
        del threshold
        content = str(memory.get("content", "")).strip()[:2000]
        normalized = self._normalize(content)
        if not normalized:
            return ""
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM memories WHERE user_id = ? AND normalized_content = ?",
                (memory["user_id"], normalized),
            ).fetchone()
            values = (
                content,
                str(memory.get("memory_type", "fact"))[:64],
                float(memory.get("importance", 0.5)),
                str(memory.get("source_session_id", "default_session"))[:128],
                int(memory.get("created_at", time.time())),
                int(memory.get("expires_at", time.time() + 90 * 86400)),
            )
            if existing:
                connection.execute(
                    """
                    UPDATE memories
                    SET content = ?, memory_type = ?, importance = MAX(importance, ?),
                        source_session_id = ?, created_at = ?, expires_at = ?
                    WHERE id = ?
                    """,
                    values + (existing["id"],),
                )
                return str(existing["id"])
            cursor = connection.execute(
                """
                INSERT INTO memories (
                    user_id, content, normalized_content, memory_type, importance,
                    source_session_id, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (memory["user_id"], content, normalized) + values[1:],
            )
            return str(cursor.lastrowid)

    def search_text(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        rows = self.list(user_id, limit=200)
        query_terms = self._terms(query)
        if not query_terms:
            return []
        for row in rows:
            overlap = len(query_terms & self._terms(row["content"]))
            row["_score"] = overlap * 2 + float(row.get("importance", 0))
        rows = [row for row in rows if row["_score"] >= 2]
        rows.sort(key=lambda row: (row["_score"], row["created_at"]), reverse=True)
        for row in rows:
            row.pop("_score", None)
        return rows[:limit]

    def list(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, memory_type, importance, source_session_id,
                       created_at, expires_at
                FROM memories
                WHERE user_id = ? AND expires_at > ?
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, int(time.time()), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, user_id: str, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE user_id = ? AND id = ?",
                (user_id, int(memory_id)),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _normalize(content: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", content).lower()

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        normalized = cls._normalize(text)
        ascii_words = set(re.findall(r"[a-z0-9]{2,}", normalized))
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        chinese_bigrams = {
            chinese[index:index + 2]
            for index in range(max(0, len(chinese) - 1))
        }
        return ascii_words | chinese_bigrams


sqlite_memory_repository = SQLiteMemoryRepository()
