"""管理 Agent 工作流生成的文件，按用户隔离并限制文件范围。"""
import json
import re
import time
import uuid
from pathlib import Path

from its_multi_agent.backend.app.config.settings import settings


class FileArtifactError(ValueError):
    pass


class FileArtifactService:
    MAX_BYTES = 2_000_000
    TTL_SECONDS = 7 * 24 * 3600
    # 这些是可直接作为文本产物保存的格式。HTML 允许生成静态网页，
    # 但仍然通过鉴权接口以附件方式下载，不把用户内容当作应用页面渲染。
    ALLOWED = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".html": "text/html",
        ".htm": "text/html",
    }

    def __init__(self, base: str | None = None):
        default = Path(__file__).resolve().parent.parent / "runtime" / "files"
        self.base = Path(base or getattr(settings, "FILE_ARTIFACT_FOLDER", None) or default)
        self.base.mkdir(parents=True, exist_ok=True)

    def create(self, user_id: str, filename: str, content: str, *, mime_type: str = "text/plain",
               session_id: str | None = None, run_id: str | None = None) -> dict:
        raw_name = str(filename or "")
        safe_name = Path(raw_name).name
        if safe_name != raw_name or "/" in raw_name or "\\" in raw_name:
            raise FileArtifactError("文件名不能包含路径")
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or safe_name in {".", ".."} or suffix not in self.ALLOWED:
            raise FileArtifactError("仅支持输出 txt、md、json、csv、html 文件")
        if mime_type != self.ALLOWED[suffix]:
            raise FileArtifactError("文件扩展名与 MIME 类型不匹配")
        payload = str(content).encode("utf-8")
        if len(payload) > self.MAX_BYTES:
            raise FileArtifactError("输出文件不能超过 2 MB")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id):
            raise FileArtifactError("无效的用户标识")
        artifact_id = uuid.uuid4().hex
        folder = self.base / user_id / artifact_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / safe_name
        temporary = folder / (safe_name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        now = int(time.time())
        metadata = {"id": artifact_id, "user_id": user_id, "filename": safe_name, "mime_type": mime_type,
                    "size": len(payload), "session_id": session_id, "run_id": run_id,
                    "created_at": now, "expires_at": now + self.TTL_SECONDS}
        (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return metadata

    def get(self, user_id: str, artifact_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{32}", artifact_id):
            raise FileArtifactError("无效的文件 ID")
        folder = self.base / user_id / artifact_id
        metadata_path = folder / "metadata.json"
        if not metadata_path.is_file():
            raise FileArtifactError("文件不存在或无权访问")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("expires_at", 0) < int(time.time()):
            self.delete(user_id, artifact_id)
            raise FileArtifactError("文件已过期")
        filename = metadata.get("filename", "")
        path = folder / filename
        if (not isinstance(filename, str) or Path(filename).name != filename
                or "/" in filename or "\\" in filename
                or Path(filename).suffix.lower() not in self.ALLOWED):
            raise FileArtifactError("文件不存在或已损坏")
        if not path.is_file() or path.resolve().parent != folder.resolve():
            raise FileArtifactError("文件不存在或已损坏")
        metadata["path"] = path
        return metadata

    def list(self, user_id: str, *, session_id: str | None = None, run_id: str | None = None) -> list[dict]:
        result = []
        for folder in (self.base / user_id).glob("*/") if (self.base / user_id).is_dir() else []:
            try:
                item = self.get(user_id, folder.name)
                if (session_id is None or item.get("session_id") == session_id) and (run_id is None or item.get("run_id") == run_id):
                    item.pop("path", None)
                    result.append(item)
            except (FileArtifactError, OSError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def delete(self, user_id: str, artifact_id: str) -> bool:
        if not re.fullmatch(r"[0-9a-f]{32}", artifact_id):
            raise FileArtifactError("无效的文件 ID")
        metadata_path = self.base / user_id / artifact_id / "metadata.json"
        if not metadata_path.is_file():
            raise FileArtifactError("文件不存在或无权访问")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = metadata.get("filename", "")
        path = metadata_path.parent / filename
        if (not isinstance(filename, str) or Path(filename).name != filename
                or "/" in filename or "\\" in filename
                or Path(filename).suffix.lower() not in self.ALLOWED):
            raise FileArtifactError("文件不存在或已损坏")
        if path.parent.resolve() != metadata_path.parent.resolve() or not path.is_file():
            raise FileArtifactError("文件不存在或已损坏")
        path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        metadata_path.parent.rmdir()
        return True


file_artifact_service = FileArtifactService()
