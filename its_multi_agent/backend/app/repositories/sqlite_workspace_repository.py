import sqlite3
from contextlib import contextmanager
from pathlib import Path
from its_multi_agent.backend.app.config.settings import settings

class SQLiteWorkspaceRepository:
    def __init__(self):
        default = Path(__file__).resolve().parent.parent / 'data' / 'workspaces.db'
        self.path = Path(getattr(settings, 'WORKSPACE_SQLITE_PATH', None) or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '', plugins_json TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(user_id, name))''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id, updated_at DESC)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10); db.row_factory = sqlite3.Row
        try:
            yield db; db.commit()
        finally: db.close()

    def list(self, user_id):
        with self._connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM workspaces WHERE user_id=? ORDER BY updated_at DESC', (user_id,)).fetchall()]

    def get(self, user_id, workspace_id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM workspaces WHERE user_id=? AND id=?', (user_id, workspace_id)).fetchone()
        return dict(row) if row else None

    def upsert_default(self, user_id, plugins):
        import json, time
        now = time.time()
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO workspaces(id,user_id,name,description,plugins_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                       ('default', user_id, '默认工作区', '通用智能服务工作区', json.dumps(plugins), now, now))
        return self.get(user_id, 'default')

    def create(self, user_id, workspace_id, name, description, plugins):
        import json, time
        now = time.time()
        with self._connect() as db:
            db.execute('INSERT INTO workspaces VALUES (?,?,?,?,?,?,?)', (workspace_id,user_id,name,description,json.dumps(plugins),now,now))
        return self.get(user_id, workspace_id)

    def delete(self, user_id, workspace_id):
        if workspace_id == 'default': return False
        with self._connect() as db:
            return db.execute('DELETE FROM workspaces WHERE user_id=? AND id=?', (user_id, workspace_id)).rowcount > 0

workspace_repository = SQLiteWorkspaceRepository()
