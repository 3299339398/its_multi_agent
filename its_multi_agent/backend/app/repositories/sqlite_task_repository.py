import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from its_multi_agent.backend.app.config.settings import settings


class SQLiteTaskRepository:
    def __init__(self, db_path: str | None = None):
        default = Path(__file__).resolve().parent.parent / "data" / "tasks.db"
        self.path = Path(db_path or getattr(settings, "TASK_SQLITE_PATH", None) or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    request_json TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
                    error TEXT, updated_at REAL NOT NULL, checkpoint_json TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    packet TEXT NOT NULL, created_at REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_tasks(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_agent_task_user_session
                    ON agent_tasks(user_id, session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_task_events_run
                    ON agent_task_events(run_id, id);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(agent_tasks)")}
            if "checkpoint_json" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN checkpoint_json TEXT")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, run_id, user_id, session_id, request, created_at):
        payload = request.model_dump(mode="json") if hasattr(request, "model_dump") else request
        # Temporary model credentials are request-scoped secrets. Never persist
        # them in the durable task queue; such tasks cannot be safely replayed.
        if isinstance(payload, dict) and payload.get("temporary_model"):
            payload = dict(payload)
            payload["temporary_model"] = None
            payload["_resume_blocked"] = "temporary_model_credentials"
        with self._connect() as db:
            db.execute("INSERT INTO agent_tasks(run_id,user_id,session_id,request_json,status,created_at,error,updated_at,checkpoint_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (run_id, user_id, session_id, json.dumps(payload, ensure_ascii=False), "queued",
                        created_at, None, created_at, None))

    def update(self, run_id, status, error=None, updated_at=None):
        import time
        with self._connect() as db:
            db.execute("UPDATE agent_tasks SET status=?, error=?, updated_at=? WHERE run_id=?",
                       (status, error, updated_at or time.time(), run_id))

    def append_event(self, run_id, packet, created_at=None):
        import time
        with self._connect() as db:
            db.execute("INSERT INTO agent_task_events(run_id, packet, created_at) VALUES (?, ?, ?)",
                       (run_id, packet, created_at or time.time()))

    def save_checkpoint(self, run_id, checkpoint):
        import time
        with self._connect() as db:
            db.execute("UPDATE agent_tasks SET checkpoint_json=?, updated_at=? WHERE run_id=?",
                       (json.dumps(checkpoint, ensure_ascii=False), time.time(), run_id))

    def get(self, run_id, user_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_tasks WHERE run_id=? AND user_id=?", (run_id, user_id)).fetchone()
        return dict(row) if row else None

    def events(self, run_id):
        with self._connect() as db:
            return [row[0] for row in db.execute(
                "SELECT packet FROM agent_task_events WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()]

    def list_for_session(self, session_id, user_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM agent_tasks WHERE user_id=? AND session_id=? ORDER BY created_at DESC",
                (user_id, session_id)
            ).fetchall()]

    def pending(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM agent_tasks WHERE status IN ('queued','running') ORDER BY created_at"
            ).fetchall()]


task_repository = SQLiteTaskRepository()
