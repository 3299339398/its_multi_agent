import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.services.conversation_memory import merge_memory, render_memory


class SQLiteSessionRepository:
    """SQLite 会话归档仓储。

    SQLite 保存完整消息，推理侧只读取由该仓储生成的摘要和最近消息。
    每次操作独立建立连接，便于 FastAPI 多线程/多协程请求安全使用。
    """

    CONTEXT_MESSAGE_LIMIT = 40
    SUMMARY_LIMIT = 6000

    def __init__(self, db_path: Optional[str] = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self._legacy_root = base_dir / "user_memories"
        self._data_dir = base_dir / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = Path(db_path or settings.SESSION_SQLITE_PATH or self._data_dir / "sessions.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._migrate_legacy_json()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
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
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, session_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id, session_id)
                        REFERENCES sessions(user_id, session_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(user_id, session_id, id);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(user_id, updated_at DESC);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(messages)")}
            if "attachments" not in columns:
                connection.execute("ALTER TABLE messages ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'")
            if "sources" not in columns:
                connection.execute("ALTER TABLE messages ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'")
            session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
            if "summary_state" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN summary_state TEXT NOT NULL DEFAULT '{}'")
            if "summary_upto_id" not in session_columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN summary_upto_id INTEGER NOT NULL DEFAULT 0")

    def load_session(self, user_id: str, session_id: str) -> Optional[List[Dict[str, Any]]]:
        with self._connect() as connection:
            session = connection.execute(
                "SELECT 1 FROM sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).fetchone()
            if session is None:
                return None
            rows = connection.execute(
                "SELECT role, content, attachments, sources FROM messages WHERE user_id = ? AND session_id = ? ORDER BY id",
                (user_id, session_id),
            ).fetchall()
            return [self._message_from_row(row) for row in rows]

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """删除用户自己的会话；消息依赖外键级联删除。"""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _message_from_row(row) -> Dict[str, Any]:
        message = {"role": row["role"], "content": row["content"]}
        attachments = json.loads(row["attachments"])
        if attachments:
            message["attachments"] = attachments
        sources = json.loads(row["sources"])
        if sources:
            message["sources"] = sources
        return message

    def load_recent_session(self, user_id: str, session_id: str, limit: int = 12) -> Optional[List[Dict[str, Any]]]:
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM sessions WHERE user_id = ? AND session_id = ?", (user_id, session_id)).fetchone() is None:
                return None
            rows = connection.execute(
                "SELECT role, content, attachments, sources FROM messages WHERE user_id = ? AND session_id = ? AND role != 'system' ORDER BY id DESC LIMIT ?",
                (user_id, session_id, max(1, min(limit, 100))),
            ).fetchall()
            return [self._message_from_row(row) for row in reversed(rows)]

    def save_session(self, user_id: str, session_id: str, data: List[Dict[str, Any]]) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(user_id, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (user_id, session_id, now, now),
            )
            connection.execute(
                "DELETE FROM messages WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
            connection.execute("UPDATE sessions SET summary = '', summary_state = '{}', summary_upto_id = 0 WHERE user_id = ? AND session_id = ?",
                               (user_id, session_id))
            connection.executemany(
                "INSERT INTO messages(user_id, session_id, role, content, created_at, attachments, sources) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (user_id, session_id, item.get("role", "assistant"), str(item.get("content", "")), now,
                     json.dumps(item.get("attachments", []), ensure_ascii=False), json.dumps(item.get("sources", []), ensure_ascii=False))
                    for item in data
                ],
            )
            self._refresh_summary(connection, user_id, session_id)

    def append_message(self, user_id: str, session_id: str, message: Dict[str, Any]) -> None:
        role = str(message.get("role", "assistant"))
        content = str(message.get("content", ""))
        attachments = json.dumps(message.get("attachments", []), ensure_ascii=False)
        sources = json.dumps(message.get("sources", []), ensure_ascii=False)
        if not content and not message.get("attachments") and not message.get("sources"):
            return

        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(user_id, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (user_id, session_id, now, now),
            )
            last = connection.execute(
                """
                SELECT role, content, attachments, sources FROM messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
            if last and last["role"] == role and last["content"] == content and last["attachments"] == attachments and last["sources"] == sources:
                return
            connection.execute(
                "INSERT INTO messages(user_id, session_id, role, content, created_at, attachments, sources) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, session_id, role, content, now, attachments, sources),
            )
            self._refresh_summary(connection, user_id, session_id)

    def get_summary(self, user_id: str, session_id: str) -> str:
        with self._connect() as connection:
            self._refresh_summary(connection, user_id, session_id)
            row = connection.execute(
                "SELECT summary FROM sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).fetchone()
            return row["summary"] if row else ""

    def get_all_sessions_metadata(self, user_id: str) -> List[Tuple[str, str, Union[List, Exception]]]:
        with self._connect() as connection:
            sessions = connection.execute(
                """
                SELECT session_id, created_at FROM sessions
                WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()

        results = []
        for session in sessions:
            try:
                data = self.load_session(user_id, session["session_id"])
                results.append((session["session_id"], session["created_at"], data or []))
            except Exception as error:
                logger.error("读取 SQLite 会话 %s 失败: %s", session["session_id"], error)
                results.append((session["session_id"], session["created_at"], error))
        return results

    def list_sessions(self, user_id: str, page: int = 1, page_size: int = 30, session_prefix: str = "") -> dict:
        page, page_size = max(1, page), max(1, min(page_size, 100))
        with self._connect() as connection:
            scope_sql = " AND session_id LIKE ?" if session_prefix else " AND session_id NOT LIKE 'ws_%__%'"
            scope_args = [session_prefix + "%"] if session_prefix else []
            total = connection.execute('SELECT COUNT(*) FROM sessions WHERE user_id = ?' + scope_sql, [user_id] + scope_args).fetchone()[0]
            rows = connection.execute('''
                SELECT s.session_id, s.created_at AS create_time, s.updated_at,
                    (SELECT substr(content, 1, 160) FROM messages m
                     WHERE m.user_id = s.user_id AND m.session_id = s.session_id AND role = 'user'
                     ORDER BY id LIMIT 1) AS title,
                    (SELECT COUNT(*) FROM messages m
                     WHERE m.user_id = s.user_id AND m.session_id = s.session_id AND role != 'system') AS total_messages
                FROM sessions s WHERE s.user_id = ?''' + scope_sql + '''
                ORDER BY s.updated_at DESC, s.session_id DESC LIMIT ? OFFSET ?
            ''', [user_id] + scope_args + [page_size, (page - 1) * page_size]).fetchall()
        return {'sessions': [dict(row) for row in rows], 'total_sessions': total,
                'next_page': page + 1 if page * page_size < total else None}

    def load_message_page(self, user_id: str, session_id: str, page_size: int = 20,
                          before_id: int | None = None) -> dict | None:
        page_size = max(1, min(page_size, 100))
        with self._connect() as connection:
            if connection.execute('SELECT 1 FROM sessions WHERE user_id = ? AND session_id = ?',
                                  (user_id, session_id)).fetchone() is None:
                return None
            cursor_sql = ' AND id < ?' if before_id is not None else ''
            parameters = [user_id, session_id] + ([before_id] if before_id is not None else []) + [page_size + 1]
            rows = connection.execute(
                "SELECT id, role, content, attachments, sources FROM messages WHERE user_id = ? AND session_id = ? "
                "AND role != 'system'" + cursor_sql + ' ORDER BY id DESC LIMIT ?', parameters,
            ).fetchall()
        visible = rows[:page_size]
        return {'messages': [dict(self._message_from_row(row), id=row['id']) for row in reversed(visible)],
                'next_before_id': visible[-1]['id'] if len(rows) > page_size else None}

    def _refresh_summary(self, connection: sqlite3.Connection, user_id: str, session_id: str) -> None:
        session = connection.execute("SELECT summary_state, summary_upto_id FROM sessions WHERE user_id = ? AND session_id = ?",
                                     (user_id, session_id)).fetchone()
        if session is None:
            return
        cutoff = connection.execute(
            "SELECT id FROM messages WHERE user_id = ? AND session_id = ? AND role != 'system' ORDER BY id DESC LIMIT 1 OFFSET ?",
            (user_id, session_id, self.CONTEXT_MESSAGE_LIMIT),
        ).fetchone()
        if cutoff is None or cutoff["id"] <= session["summary_upto_id"]:
            return
        rows = connection.execute(
            """
            SELECT id, role, content FROM messages
            WHERE user_id = ? AND session_id = ? AND id > ? AND id <= ? AND role != 'system'
            ORDER BY id
            """,
            (user_id, session_id, session["summary_upto_id"], cutoff["id"]),
        ).fetchall()
        state = merge_memory(json.loads(session["summary_state"]), rows)
        summary = render_memory(state)
        connection.execute(
            "UPDATE sessions SET summary = ?, summary_state = ?, summary_upto_id = ? WHERE user_id = ? AND session_id = ? AND summary_upto_id = ?",
            (summary, json.dumps(state, ensure_ascii=False), cutoff["id"], user_id, session_id, session["summary_upto_id"]),
        )

    def _migrate_legacy_json(self) -> None:
        if not self._legacy_root.exists():
            return
        for file_path in self._legacy_root.glob("*/*.json"):
            user_id = file_path.parent.name
            session_id = file_path.stem
            try:
                with file_path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                with self._connect() as connection:
                    exists = connection.execute(
                        "SELECT 1 FROM sessions WHERE user_id = ? AND session_id = ?",
                        (user_id, session_id),
                    ).fetchone()
                if not exists and isinstance(data, list):
                    self.save_session(user_id, session_id, data)
                    logger.info("已迁移旧会话: %s/%s", user_id, session_id)
            except Exception as error:
                logger.warning("迁移旧会话失败 %s: %s", file_path, error)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")


session_repository = SQLiteSessionRepository()
