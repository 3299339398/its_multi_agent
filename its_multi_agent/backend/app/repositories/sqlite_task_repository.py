import json
import sqlite3
import time
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from its_multi_agent.backend.app.config.settings import settings


execution_lease = ContextVar("execution_lease", default=None)


class TaskLeaseLost(RuntimeError):
    """旧执行者不得在租约失效后继续提交结果。"""


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
                    error TEXT, updated_at REAL NOT NULL, checkpoint_json TEXT,
                    execution_checkpoint_json TEXT,
                    lease_owner TEXT, lease_expires_at REAL, attempt_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS agent_task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    packet TEXT NOT NULL, created_at REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_tasks(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS agent_tool_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    user_id TEXT,
                    project_id TEXT,
                    tool_name TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL,
                    permitted INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    side_effect_level TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_task_user_session
                    ON agent_tasks(user_id, session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_task_events_run
                    ON agent_task_events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_agent_tool_audits_run
                    ON agent_tool_audits(run_id, id);
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(agent_tasks)")}
            if "checkpoint_json" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN checkpoint_json TEXT")
            if "execution_checkpoint_json" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN execution_checkpoint_json TEXT")
            if "lease_owner" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN lease_owner TEXT")
            if "lease_expires_at" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN lease_expires_at REAL")
            if "attempt_count" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "event_start_id" not in columns:
                db.execute("ALTER TABLE agent_tasks ADD COLUMN event_start_id INTEGER NOT NULL DEFAULT 0")

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
        # 临时模型凭据仅用于当前请求，不写入持久化任务队列；
        # 缺少这些凭据的任务不能在重启后安全重放。
        if isinstance(payload, dict) and payload.get("temporary_model"):
            payload = dict(payload)
            payload["temporary_model"] = None
            payload["_resume_blocked"] = "temporary_model_credentials"
        with self._connect() as db:
            db.execute("INSERT INTO agent_tasks(run_id,user_id,session_id,request_json,status,created_at,error,updated_at,checkpoint_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (run_id, user_id, session_id, json.dumps(payload, ensure_ascii=False), "queued",
                        created_at, None, created_at, None))

    def update(self, run_id, status, error=None, updated_at=None):
        with self._connect() as db:
            self._assert_lease(db, run_id)
            db.execute("UPDATE agent_tasks SET status=?, error=?, updated_at=? WHERE run_id=?",
                       (status, error, updated_at or time.time(), run_id))

    def claim(self, run_id: str, owner: str, lease_seconds: int = 90) -> bool:
        """以数据库条件更新领取任务，避免多实例同时执行同一 run。"""
        now = time.time()
        with self._connect() as db:
            result = db.execute(
                """UPDATE agent_tasks
                   SET lease_owner=?, lease_expires_at=?, attempt_count=attempt_count+1,
                       updated_at=?
                   WHERE run_id=? AND status='queued'
                     AND (lease_owner IS NULL OR lease_expires_at IS NULL OR lease_expires_at<?)""",
                (owner, now + lease_seconds, now, run_id, now),
            )
            return result.rowcount == 1

    def renew_lease(self, run_id: str, owner: str, lease_seconds: int = 90) -> bool:
        now = time.time()
        with self._connect() as db:
            result = db.execute(
                "UPDATE agent_tasks SET lease_expires_at=?, updated_at=? WHERE run_id=? AND lease_owner=? AND lease_expires_at>? AND status IN ('queued','running')",
                (now + lease_seconds, now, run_id, owner, now),
            )
            return result.rowcount == 1

    def release_lease(self, run_id: str, owner: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE agent_tasks SET lease_owner=NULL, lease_expires_at=NULL, updated_at=? WHERE run_id=? AND lease_owner=?",
                (time.time(), run_id, owner),
            )

    def append_event(self, run_id, packet, created_at=None):
        with self._connect() as db:
            self._assert_lease(db, run_id)
            db.execute("INSERT INTO agent_task_events(run_id, packet, created_at) VALUES (?, ?, ?)",
                       (run_id, packet, created_at or time.time()))

    def append_tool_audit(self, audit: dict, created_at=None):
        """保存不含工具参数和返回内容的策略判定摘要。"""
        import time
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO agent_tool_audits(
                    run_id, user_id, project_id, tool_name, allowed, confirmed,
                    permitted, risk_level, side_effect_level, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.get("run_id"), audit.get("user_id"), audit.get("project_id"),
                    str(audit.get("tool_name", ""))[:128], int(bool(audit.get("allowed"))),
                    int(bool(audit.get("confirmed"))), int(bool(audit.get("permitted"))),
                    str(audit.get("risk_level", "medium"))[:16],
                    str(audit.get("side_effect_level", "external"))[:16],
                    str(audit.get("reason", ""))[:500], created_at or time.time(),
                ),
            )

    def save_checkpoint(self, run_id, checkpoint):
        with self._connect() as db:
            self._assert_lease(db, run_id)
            db.execute("UPDATE agent_tasks SET checkpoint_json=?, updated_at=? WHERE run_id=?",
                       (json.dumps(checkpoint, ensure_ascii=False), time.time(), run_id))

    def save_execution_checkpoint(self, run_id, checkpoint):
        """保存复杂任务的步骤状态，不覆盖面向前端的计划快照。"""
        import time
        with self._connect() as db:
            self._assert_lease(db, run_id)
            db.execute(
                "UPDATE agent_tasks SET execution_checkpoint_json=?, updated_at=? WHERE run_id=?",
                (json.dumps(checkpoint, ensure_ascii=False), time.time(), run_id),
            )

    def execution_checkpoint(self, run_id, user_id=None):
        with self._connect() as db:
            query = "SELECT execution_checkpoint_json FROM agent_tasks WHERE run_id=?"
            params = [run_id]
            if user_id is not None:
                query += " AND user_id=?"
                params.append(user_id)
            row = db.execute(query, params).fetchone()
        if not row or not row[0]:
            return None
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def get(self, run_id, user_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_tasks WHERE run_id=? AND user_id=?", (run_id, user_id)).fetchone()
        return dict(row) if row else None

    def events(self, run_id):
        return [row["packet"] for row in self.event_rows(run_id)]

    def event_rows(self, run_id, after_id=0, limit=None):
        with self._connect() as db:
            query = """SELECT id, packet FROM agent_task_events WHERE run_id=?
                       AND id>MAX(?, COALESCE((SELECT event_start_id FROM agent_tasks WHERE run_id=?),0))
                       ORDER BY id"""
            params = [run_id, after_id, run_id]
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            return [dict(row) for row in db.execute(query, params).fetchall()]

    @staticmethod
    def _assert_lease(db, run_id):
        lease = execution_lease.get()
        if not lease or lease[0] != run_id:
            return
        # BEGIN IMMEDIATE makes the ownership check and write one transaction.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT lease_owner, lease_expires_at, status FROM agent_tasks WHERE run_id=?", (run_id,)).fetchone()
        if not row or row[0] != lease[1] or (row[1] or 0) <= time.time() or row[2] not in {'queued', 'running'}:
            raise TaskLeaseLost("任务执行租约已失效")

    def assert_execution_lease(self, run_id):
        with self._connect() as db:
            self._assert_lease(db, run_id)

    def queue_resume(self, run_id, user_id):
        with self._connect() as db:
            result = db.execute("""UPDATE agent_tasks SET status='queued', error=NULL,
                lease_owner=NULL, lease_expires_at=NULL, updated_at=?,
                event_start_id=COALESCE((SELECT MAX(id) FROM agent_task_events WHERE run_id=?),0)
                WHERE run_id=? AND user_id=? AND status IN ('failed','cancelled')
                AND (lease_expires_at IS NULL OR lease_expires_at<=?)""",
                (time.time(), run_id, run_id, user_id, time.time()))
            return result.rowcount == 1

    def fail_expired(self, run_id, message):
        with self._connect() as db:
            result = db.execute("""UPDATE agent_tasks SET status='failed', error=?, updated_at=?,
                lease_owner=NULL, lease_expires_at=NULL WHERE run_id=? AND status IN ('queued','running')
                AND (lease_expires_at IS NULL OR lease_expires_at<=?)""",
                (message, time.time(), run_id, time.time()))
            return result.rowcount == 1

    def request_cancel(self, run_id, user_id):
        with self._connect() as db:
            result = db.execute("""UPDATE agent_tasks SET status='cancelled', error='任务已取消', updated_at=?
                WHERE run_id=? AND user_id=? AND status IN ('queued','running')""",
                (time.time(), run_id, user_id))
            return result.rowcount == 1

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
