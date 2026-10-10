"""受限代码工作区的读取、修改和检查服务。"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
import hashlib
import sqlite3
import time
from functools import wraps
from contextlib import closing
from pathlib import Path

from its_multi_agent.backend.app.config.settings import settings

from its_multi_agent.backend.app.repositories.sqlite_task_repository import execution_lease, task_repository

def serialized_mutation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        # SQLite transaction is an OS/process lock shared by all API workers.
        with closing(sqlite3.connect(self._operation_db().with_name("workspace_locks.db"), timeout=60)) as lock, lock:
            lock.execute("BEGIN IMMEDIATE")
            lease = execution_lease.get()
            if lease:
                task_repository.assert_execution_lease(lease[0])
            return method(self, *args, **kwargs)
    return guarded


class CodeWorkspaceError(ValueError):
    """代码工作区请求无效或超出授权边界。"""


class CodeWorkspaceService:
    MAX_FILE_BYTES = 512 * 1024
    MAX_RESULT_CHARS = 30_000
    MAX_FILES = 500
    EXCLUDED_PARTS = {
        ".git", ".idea", ".pytest_cache", ".venv", "venv", "node_modules",
        "dist", "build", "__pycache__", "runtime", "logs",
    }
    ALLOWED_SUFFIXES = {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".vue", ".css", ".scss",
        ".html", ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".sql",
        ".sh", ".ps1", ".bat", ".ini", ".cfg", ".properties",
    }
    ALLOWED_NAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore"}

    def __init__(self, root: str | Path, *, actor: str = "local"):
        if not root:
            raise CodeWorkspaceError("服务端未配置代码工作区")
        self.actor = actor
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise CodeWorkspaceError("代码工作区不是有效目录")

    def _resolve(self, relative_path: str, *, must_exist: bool = True) -> Path:
        raw = str(relative_path or ".").replace("\\", "/").strip()
        if not raw or Path(raw).is_absolute() or re.match(r"^[A-Za-z]:", raw):
            raise CodeWorkspaceError("路径必须是工作区内的相对路径")
        if any(part.casefold() in self.EXCLUDED_PARTS for part in Path(raw).parts):
            raise CodeWorkspaceError("该目录不允许访问")
        try:
            candidate = (self.root / raw).resolve(strict=must_exist)
        except OSError as error:
            raise CodeWorkspaceError("路径不存在或无法访问") from error
        if candidate != self.root and self.root not in candidate.parents:
            raise CodeWorkspaceError("路径超出授权工作区")
        return candidate

    def _check_file(self, path: Path) -> None:
        if path.name not in self.ALLOWED_NAMES and path.suffix.lower() not in self.ALLOWED_SUFFIXES:
            raise CodeWorkspaceError("该文件类型不允许访问")
        if path.exists() and (not path.is_file() or path.stat().st_size > self.MAX_FILE_BYTES):
            raise CodeWorkspaceError("文件不存在、不是普通文件或超过大小限制")

    def list_files(self, relative_path: str = ".") -> dict:
        base = self._resolve(relative_path)
        if not base.is_dir():
            raise CodeWorkspaceError("列表路径必须是目录")
        files = []
        for path in base.rglob("*"):
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                continue
            if any(part.casefold() in self.EXCLUDED_PARTS for part in relative.parts):
                continue
            if not path.is_symlink() and path.is_file() and (path.name in self.ALLOWED_NAMES or path.suffix.lower() in self.ALLOWED_SUFFIXES):
                files.append(relative.as_posix())
                if len(files) >= self.MAX_FILES:
                    break
        return {"status": "ok", "files": sorted(files), "truncated": len(files) >= self.MAX_FILES}

    def read_file(self, relative_path: str, start_line: int = 1, end_line: int = 400) -> dict:
        path = self._resolve(relative_path)
        self._check_file(path)
        if start_line < 1 or end_line < start_line or end_line - start_line > 799:
            raise CodeWorkspaceError("行号范围无效，单次最多读取 800 行")
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        selected = lines[start_line - 1:end_line]
        content = "\n".join(f"{number}: {line}" for number, line in enumerate(selected, start_line))
        canonical_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return {"status": "ok", "path": relative_path, "start_line": start_line,
                "end_line": min(end_line, len(lines)), "content": content[:self.MAX_RESULT_CHARS],
                "sha256": canonical_sha256}

    def search(self, query: str, relative_path: str = ".") -> dict:
        if not query or len(query) > 500:
            raise CodeWorkspaceError("搜索词长度无效")
        base = self._resolve(relative_path)
        candidates = [base] if base.is_file() else base.rglob("*")
        matches = []
        for path in candidates:
            relative = path.relative_to(self.root)
            if any(part.casefold() in self.EXCLUDED_PARTS for part in relative.parts) or path.is_symlink() or not path.is_file():
                continue
            if path.name not in self.ALLOWED_NAMES and path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                continue
            if path.stat().st_size > self.MAX_FILE_BYTES:
                continue
            try:
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({"path": relative.as_posix(), "line": number, "text": line[:500]})
                        if len(matches) >= 100:
                            return {"status": "ok", "matches": matches, "truncated": True}
            except UnicodeDecodeError:
                continue
        return {"status": "ok", "matches": matches, "truncated": False}

    @serialized_mutation
    def replace(self, relative_path: str, old_text: str, new_text: str,
                *, expected_sha256: str = "", operation_id: str = "") -> dict:
        path = self._resolve(relative_path)
        self._check_file(path)
        if not old_text or old_text == new_text:
            raise CodeWorkspaceError("必须提供不相同的原文和新内容")
        original = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        operation_id = operation_id.strip() or hashlib.sha256(
            f"replace\0{relative_path}\0{old_text}\0{new_text}\0{expected_sha256}".encode("utf-8")
        ).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(
            [str(self.root), self.actor, path.relative_to(self.root).as_posix(), old_text, new_text, expected_sha256],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        cache_key = hashlib.sha256(f"{self.root}\0{self.actor}\0{operation_id}".encode("utf-8")).hexdigest()
        prior = self._operation_get(cache_key)
        if prior is not None:
            if prior.get("request_fingerprint") != fingerprint:
                raise CodeWorkspaceError("operation_id 已被其他修改请求使用")
            if prior.get("status") == "pending":
                raise CodeWorkspaceError("上次修改结果不确定，请检查文件后使用新的 operation_id")
            return prior
        if expected_sha256 and expected_sha256.casefold() != digest:
            raise CodeWorkspaceError("目标文件版本已变化，请重新读取后再修改")
        occurrences = original.count(old_text)
        if occurrences != 1:
            raise CodeWorkspaceError(f"原文必须精确匹配一次，当前匹配 {occurrences} 次")
        updated = original.replace(old_text, new_text, 1)
        if len(updated.encode("utf-8")) > self.MAX_FILE_BYTES:
            raise CodeWorkspaceError("替换后的文件超过大小限制")
        self._operation_put(cache_key, {"status": "pending", "request_fingerprint": fingerprint})
        self._atomic_write(path, updated)
        result = self._change_result(relative_path, original, updated)
        result["operation_id"] = operation_id
        result["before_sha256"] = digest
        result["after_sha256"] = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        result["request_fingerprint"] = fingerprint
        self._operation_put(cache_key, result)
        return result

    @staticmethod
    def _operation_db() -> Path:
        base = Path(__file__).resolve().parent.parent / "data"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "workspace_operations.db"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS operations (operation_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at REAL NOT NULL)")
        return path

    def _operation_get(self, operation_id: str) -> dict | None:
        path = self._operation_db()
        with closing(sqlite3.connect(path)) as db, db:
            row = db.execute("SELECT result_json FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
            value["idempotent_replay"] = True
            return value
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _operation_put(self, operation_id: str, result: dict) -> None:
        path = self._operation_db()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO operations(operation_id,result_json,created_at) VALUES(?,?,?)",
                (operation_id, json.dumps(result, ensure_ascii=False), time.time()),
            )

    @serialized_mutation
    def create(self, relative_path: str, content: str) -> dict:
        path = self._resolve(relative_path, must_exist=False)
        self._check_file(path)
        if path.exists():
            raise CodeWorkspaceError("文件已存在，请使用精确替换")
        if len(content.encode("utf-8")) > self.MAX_FILE_BYTES:
            raise CodeWorkspaceError("文件内容超过大小限制")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, content)
        return self._change_result(relative_path, "", content)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _change_result(self, relative_path: str, before: str, after: str) -> dict:
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}", tofile=f"b/{relative_path}", n=3,
        ))
        return {"status": "ok", "path": relative_path, "changed": True,
                "diff": diff[:self.MAX_RESULT_CHARS], "diff_truncated": len(diff) > self.MAX_RESULT_CHARS}

    def run_check(self, name: str) -> dict:
        commands = json.loads(settings.CODE_CHECK_COMMANDS_JSON)
        command = commands.get(name)
        if not command:
            raise CodeWorkspaceError("未知或未配置的检查命令")
        command = list(command)
        executable = Path(command[0])
        if not executable.is_absolute() and (self.root / executable).is_file():
            command[0] = str((self.root / executable).resolve())
        try:
            # 检查命令运行在受限环境中，避免把 API Key、JWT 和数据库凭据
            # 从服务进程环境继承给工程脚本。
            process_env = {
                key: value for key, value in os.environ.items()
                if key.casefold() in {"path", "pathext", "systemroot", "windir", "temp", "tmp"}
            }
            process_env["PYTHONPATH"] = str(self.root.parent)
            completed = subprocess.run(
                command, cwd=self.root, shell=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=settings.CODE_STEP_TIMEOUT_SECONDS,
                env=process_env,
            )
            output = (completed.stdout + completed.stderr)[-self.MAX_RESULT_CHARS:]
            return {"status": "ok" if completed.returncode == 0 else "failed", "name": name,
                    "exit_code": completed.returncode, "output": output,
                    "output_truncated": len(completed.stdout + completed.stderr) > self.MAX_RESULT_CHARS}
        except subprocess.TimeoutExpired as error:
            # TimeoutExpired may retain bytes even when subprocess.run uses text=True.
            output = "".join(
                value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
                for value in (error.stdout, error.stderr)
            )
            return {"status": "timeout", "name": name,
                    "output": output[-self.MAX_RESULT_CHARS:],
                    "output_truncated": len(output) > self.MAX_RESULT_CHARS}
        except OSError:
            return {"status": "failed", "name": name, "exit_code": None,
                    "output": "预设检查命令无法启动"}
