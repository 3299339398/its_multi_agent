import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from its_multi_agent.backend.app.config.settings import settings


class UserRepository:
    """Persistent application users stored separately from chat archives."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "users.db"
        self._db_path = Path(db_path or settings.USER_SQLITE_PATH or default_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_if_missing(
        self, user_id: str, username: str, password_hash: str, role: str = "user",
    ) -> bool:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO users(
                    user_id, username, password_hash, role, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (user_id, username, password_hash, role, now, now),
            )
            return cursor.rowcount > 0

    def create_user(
        self, user_id: str, username: str, password_hash: str, role: str = "user",
    ) -> bool:
        """Create a user and report whether the insert succeeded."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO users(
                    user_id, username, password_hash, role, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (user_id, username, password_hash, role, now, now),
            )
            return cursor.rowcount > 0

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role, is_active FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role, is_active FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_role(self, user_id: str, role: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE user_id = ?",
                (role, datetime.now().isoformat(timespec="seconds"), user_id),
            )

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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "role" not in columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
                )


user_repository = UserRepository()
