from pathlib import Path
import re
import json
import uuid
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from starlette.responses import JSONResponse, StreamingResponse, FileResponse

from its_multi_agent.backend.app.api.dependencies import get_current_admin, get_current_user
from its_multi_agent.backend.app.config.settings import settings
from its_multi_agent.backend.app.infrastructure.logging.logger import logger
from its_multi_agent.backend.app.schemas.request import (
    ChatMessageRequest,
    KnowledgeQueryRequest,
    LoginRequest,
    RegisterRequest,
    WorkspaceCreateRequest,
)
from its_multi_agent.backend.app.services.agent_service import MultiAgentService
from its_multi_agent.backend.app.services.auth_service import AuthConfigurationError, UserAlreadyExistsError, auth_service
from its_multi_agent.backend.app.services.memory_service import memory_service
from its_multi_agent.backend.app.services.session_service import session_service
from its_multi_agent.backend.app.infrastructure.ai.model_factory import list_profiles
from its_multi_agent.backend.app.schemas.model_profile import ModelProfilePublic
from its_multi_agent.backend.app.plugins import plugin_registry
from its_multi_agent.backend.app.projects import list_projects
from its_multi_agent.backend.app.services.attachment_service import (
    AttachmentError, attachment_service,
)
from its_multi_agent.backend.app.services.task_manager import task_manager
from its_multi_agent.backend.app.repositories.sqlite_workspace_repository import workspace_repository
from its_multi_agent.backend.app.repositories.model_profile_repository import DuplicateModelProfileError, user_model_profiles
from its_multi_agent.backend.app.schemas.model_profile import ModelProfileCreate
from its_multi_agent.backend.app.schemas.file_artifact import FileArtifactCreateRequest
from its_multi_agent.backend.app.services.file_artifact_service import file_artifact_service, FileArtifactError
from its_multi_agent.backend.app.services.file_preview_service import issue_preview_ticket, verify_preview_ticket


router = APIRouter()
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _artifact_public(item):
    return {key: item[key] for key in ("id", "filename", "mime_type", "size", "session_id", "run_id", "created_at", "expires_at")} | {
        "download_url": f"/api/files/{item['id']}/download"
    }


@router.post("/api/files", summary="Create a user-scoped text file")
def create_file_artifact(request: FileArtifactCreateRequest, user: Dict[str, str] = Depends(get_current_user)):
    try:
        item = file_artifact_service.create(user["user_id"], request.filename, request.content,
                                            mime_type=request.mime_type, session_id=request.session_id, run_id=request.run_id)
    except FileArtifactError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _artifact_public(item)


@router.get("/api/files", summary="List current user's generated files")
def list_file_artifacts(session_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$"),
                        run_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]+$"),
                        user: Dict[str, str] = Depends(get_current_user)):
    return {"files": [_artifact_public(item) for item in file_artifact_service.list(user["user_id"], session_id=session_id, run_id=run_id)]}


@router.get("/api/files/{artifact_id}", summary="Get generated file metadata")
def get_file_artifact(artifact_id: str, user: Dict[str, str] = Depends(get_current_user)):
    try:
        return _artifact_public(file_artifact_service.get(user["user_id"], artifact_id))
    except FileArtifactError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/files/{artifact_id}/download", summary="Download a generated file")
def download_file_artifact(artifact_id: str, user: Dict[str, str] = Depends(get_current_user)):
    try:
        item = file_artifact_service.get(user["user_id"], artifact_id)
    except FileArtifactError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FileResponse(
        item["path"], media_type=item["mime_type"], filename=item["filename"],
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.delete("/api/files/{artifact_id}", summary="Delete a generated file")
def delete_file_artifact(artifact_id: str, user: Dict[str, str] = Depends(get_current_user)):
    try:
        file_artifact_service.delete(user["user_id"], artifact_id)
    except FileArtifactError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"deleted": True, "id": artifact_id}


@router.post("/api/files/{artifact_id}/preview-ticket")
def create_preview_ticket(artifact_id: str, user: Dict[str, str] = Depends(get_current_user)):
    try:
        item = file_artifact_service.get(user["user_id"], artifact_id)
        if item["mime_type"] != "text/html":
            raise FileArtifactError("仅支持 HTML 预览")
        ticket = issue_preview_ticket(user["user_id"], artifact_id)
    except (FileArtifactError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse({"preview_url": f"/api/file-previews/{ticket}"}, headers={"Cache-Control": "no-store"})


@router.get("/api/file-previews/{ticket}")
def preview_file_artifact(ticket: str):
    try:
        user_id, artifact_id = verify_preview_ticket(ticket)
        item = file_artifact_service.get(user_id, artifact_id)
        if item["mime_type"] != "text/html":
            raise FileArtifactError("仅支持 HTML 预览")
    except (FileArtifactError, ValueError) as error:
        raise HTTPException(status_code=404, detail="预览不存在或已过期") from error
    return FileResponse(item["path"], media_type="text/html", headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'",
    })


@router.post("/api/attachments", summary="Upload a chat attachment")
async def upload_chat_attachment(
    file: UploadFile = File(...),
    user: Dict[str, str] = Depends(get_current_user),
):
    try:
        item = await attachment_service.save(user["user_id"], file)
    except AttachmentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {key: item[key] for key in ("id", "name", "kind", "media_type", "size", "sha256")}


@router.delete("/api/attachments/{attachment_id}", summary="Delete a chat attachment")
def delete_chat_attachment(attachment_id: str, user: Dict[str, str] = Depends(get_current_user)):
    try:
        attachment_service.delete(user["user_id"], attachment_id)
    except AttachmentError as error:
        raise HTTPException(status_code=404, detail="附件不存在或已删除") from error
    except OSError as error:
        raise HTTPException(status_code=500, detail="附件删除失败，请稍后重试") from error
    return {"deleted": True, "id": attachment_id}


@router.post("/api/auth/login", summary="User login")
def login(request: LoginRequest):
    user = auth_service.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    try:
        token = auth_service.issue_token(user)
    except AuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_MINUTES * 60,
        "user": user,
    }


@router.post("/api/auth/register", summary="Register a client user")
def register(request: RegisterRequest):
    try:
        user = auth_service.register(request.username, request.password)
        token = auth_service.issue_token(user)
    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail="用户名已存在") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_MINUTES * 60,
        "user": user,
    }


@router.get("/api/auth/me", summary="Current user")
def current_user(user: Dict[str, str] = Depends(get_current_user)):
    return {"user": user}


@router.get("/api/model-profiles", summary="Available model profiles")
def available_model_profiles(user: Dict[str, str] = Depends(get_current_user)):
    """仅公开模型元数据，凭据始终保留在服务端。"""
    profiles = []
    for profile in list_profiles():
        data = profile.model_dump(exclude={"api_key", "base_url"})
        profiles.append(ModelProfilePublic.model_validate(data))
    return {"profiles": profiles + user_model_profiles.list_public(user["user_id"])}


@router.post("/api/model-profiles", summary="Save a personal model profile")
def save_model_profile(request: ModelProfileCreate, user: Dict[str, str] = Depends(get_current_user)):
    if len(request.api_key) < 8:
        raise HTTPException(status_code=400, detail="API Key 长度不合法")
    try:
        profile_id = user_model_profiles.save(user["user_id"], request.model_dump())
    except DuplicateModelProfileError as error:
        raise HTTPException(status_code=409, detail="同名模型配置已存在") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="模型地址或配置无效，请选择管理员已批准的模型服务地址。") from error
    return {"id": profile_id, "name": request.name, "message": "模型配置已保存"}


@router.delete("/api/model-profiles/{profile_id}", summary="Delete a personal model profile")
def delete_model_profile(profile_id: str, user: Dict[str, str] = Depends(get_current_user)):
    if not profile_id.startswith("user-") or not user_model_profiles.delete(user["user_id"], profile_id):
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return {"message": "模型配置已删除"}


@router.get("/api/plugins", summary="Available agent plugins")
def available_plugins(_user: Dict[str, str] = Depends(get_current_user)):
    return {
        "plugins": [
            {
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "tools": list(plugin.tools),
                "capabilities": list(plugin.capabilities),
                "requires_confirmation": plugin.requires_confirmation,
                "enabled_by_default": plugin.enabled_by_default,
            }
            for plugin in plugin_registry.list_plugins()
        ]
    }


@router.get("/api/projects", summary="Available projects")
def available_projects(_user: Dict[str, str] = Depends(get_current_user)):
    return {"projects": [
        {"id": project.id, "name": project.name, "description": project.description,
         "plugins": list(project.plugins)}
        for project in list_projects()
    ]}


@router.get("/api/workspaces", summary="List current user's workspaces")
def list_workspaces(user: Dict[str, str] = Depends(get_current_user)):
    plugins = [plugin.id for plugin in plugin_registry.list_plugins()]
    rows = workspace_repository.list(user["user_id"])
    if not rows:
        rows = [workspace_repository.upsert_default(user["user_id"], plugins)]
    return {"workspaces": [_workspace_public(row) for row in rows]}


@router.post("/api/workspaces", summary="Create a workspace")
def create_workspace(request: WorkspaceCreateRequest, user: Dict[str, str] = Depends(get_current_user)):
    known = {plugin.id for plugin in plugin_registry.list_plugins()}
    unknown = set(request.plugins) - known
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知工具: {', '.join(sorted(unknown))}")
    workspace_id = uuid.uuid4().hex[:16]
    try:
        row = workspace_repository.create(user["user_id"], workspace_id, request.name, request.description, request.plugins)
    except Exception as error:
        raise HTTPException(status_code=409, detail="工作区名称已存在") from error
    return _workspace_public(row)


@router.delete("/api/workspaces/{workspace_id}", summary="Delete a workspace")
def delete_workspace(workspace_id: str, user: Dict[str, str] = Depends(get_current_user)):
    if not workspace_repository.delete(user["user_id"], workspace_id):
        raise HTTPException(status_code=400 if workspace_id == "default" else 404, detail="默认工作区不可删除或工作区不存在")
    return {"deleted": True, "workspace_id": workspace_id}


def _workspace_public(row):
    return {"id": row["id"], "name": row["name"], "description": row["description"],
            "plugins": json.loads(row["plugins_json"] or "[]"), "created_at": row["created_at"]}


@router.post("/api/query", summary="Agent chat")
async def query(
    request_context: ChatMessageRequest,
    user: Dict[str, str] = Depends(get_current_user),
) -> StreamingResponse:
    logger.info("用户 %s 发送任务", user["user_id"])
    run_id = await task_manager.start(request_context, user["user_id"])

    async def stream():
        # 通过轻量元数据事件，让重连客户端可将事件流关联到对应任务。
        # 现有客户端可安全忽略此事件。
        yield "data: " + json.dumps({"task": {"run_id": run_id, "session_id": request_context.context.session_id}}, ensure_ascii=False) + "\n\n"
        async for packet in task_manager.subscribe(run_id, user["user_id"]):
            yield packet
    return StreamingResponse(
        content=stream(),
        status_code=200,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/tasks/{run_id}", summary="Get chat task status")
def get_task_status(run_id: str, user: Dict[str, str] = Depends(get_current_user)):
    result = task_manager.get(run_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@router.get("/api/tasks/{run_id}/events", summary="Replay or subscribe to chat task events")
async def task_events(run_id: str, user: Dict[str, str] = Depends(get_current_user)):
    if task_manager.get(run_id, user["user_id"]) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StreamingResponse(task_manager.subscribe(run_id, user["user_id"]), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/sessions/{session_id}/tasks", summary="List chat tasks for a session")
def session_tasks(session_id: str, user: Dict[str, str] = Depends(get_current_user)):
    return {"tasks": task_manager.list_for_session(session_id, user["user_id"])}


@router.post("/api/tasks/{run_id}/cancel", summary="Cancel a chat task")
async def cancel_task(run_id: str, user: Dict[str, str] = Depends(get_current_user)):
    if not await task_manager.cancel(run_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"run_id": run_id, "status": "cancelled"}


@router.post("/api/tasks/{run_id}/resume", summary="Resume a failed task from its checkpoint")
async def resume_task(run_id: str, user: Dict[str, str] = Depends(get_current_user)):
    """显式恢复已失败任务；不在服务启动时自动重放有副作用步骤。"""
    try:
        return await task_manager.resume(run_id, user["user_id"])
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/api/user_sessions", summary="Current user's chat archives")
def get_user_sessions(user: Dict[str, str] = Depends(get_current_user),
                      page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                      workspace_id: str = Query("default", pattern=r"^[A-Za-z0-9_-]+$")):
    user_id = user["user_id"]
    try:
        result = session_service.list_sessions(user_id, page, page_size, workspace_id)
        return {
            "success": True,
            "user_id": user_id,
            **result,
        }
    except Exception as error:
        logger.exception("读取用户 %s 的会话失败", user_id)
        raise HTTPException(status_code=500, detail="读取会话失败") from error


@router.get("/api/sessions/{session_id}/messages", summary="Current user's paged session messages")
def get_session_messages(session_id: str, page_size: int = Query(20, ge=1, le=100),
                         before_id: int | None = Query(None, ge=1),
                         workspace_id: str = Query("default", pattern=r"^[A-Za-z0-9_-]+$"),
                         user: Dict[str, str] = Depends(get_current_user)):
    result = session_service.load_message_page(user['user_id'], session_id, page_size, before_id, workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.delete("/api/sessions/{session_id}", summary="Delete current user's chat archive")
def delete_user_session(session_id: str, workspace_id: str = Query("default", pattern=r"^[A-Za-z0-9_-]+$"),
                        user: Dict[str, str] = Depends(get_current_user)):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(status_code=400, detail="非法的会话 ID")
    if not session_service.delete_session(user["user_id"], session_id, workspace_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "user_id": user["user_id"], "session_id": session_id}


@router.get("/api/memories", summary="Current user's long-term memories")
def get_user_memories(workspace_id: str = Query("default", pattern=r"^[A-Za-z0-9_-]+$"), user: Dict[str, str] = Depends(get_current_user)):
    if not memory_service.available:
        raise HTTPException(status_code=503, detail="长期记忆服务暂时不可用")
    user_id = user["user_id"]
    return {
        "success": True,
        "user_id": user_id,
        "memories": memory_service.list_memories(user_id, workspace_id),
    }


@router.delete("/api/memories/{memory_id}", summary="Delete a long-term memory")
def delete_user_memory(
    memory_id: int,
    workspace_id: str = Query("default", pattern=r"^[A-Za-z0-9_-]+$"),
    user: Dict[str, str] = Depends(get_current_user),
):
    if memory_id <= 0:
        raise HTTPException(status_code=400, detail="非法的记忆 ID")
    if not memory_service.available:
        raise HTTPException(status_code=503, detail="长期记忆服务暂时不可用")
    user_id = user["user_id"]
    if not memory_service.delete_memory(user_id, memory_id, workspace_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "user_id": user_id, "memory_id": memory_id}


@router.post("/api/knowledge/query", summary="Authenticated knowledge query")
async def query_knowledge(
    request: KnowledgeQueryRequest,
    _user: Dict[str, str] = Depends(get_current_user),
):
    return await _forward_knowledge_request("/query", json=request.model_dump())


@router.post("/api/knowledge/upload", summary="Authenticated knowledge upload")
async def upload_knowledge_document(
    file: UploadFile = File(...),
    knowledge_space: str = Form(
        "default", min_length=1, max_length=64, pattern=r"^[\w.-]+$",
    ),
    domain: str = Form(
        "general", min_length=1, max_length=64, pattern=r"^[\w.-]+$",
    ),
    user: Dict[str, str] = Depends(get_current_admin),
):
    file_name = Path(file.filename or "").name
    if not file_name or Path(file_name).suffix.lower() not in {".md", ".txt", ".pdf", ".docx", ".xlsx"}:
        raise HTTPException(status_code=400, detail="仅支持 .md、.txt、.pdf、.docx、.xlsx 文件")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10 MB")
    return await _forward_knowledge_request(
        "/upload",
        files={"file": (file_name, content, file.content_type or "application/octet-stream")},
        data={
            "knowledge_space": knowledge_space,
            "domain": domain,
            "uploaded_by": user["username"],
        },
    )


@router.get("/api/knowledge/documents", summary="Admin knowledge documents")
async def list_knowledge_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    status: str = Query("", max_length=32),
    knowledge_space: str = Query("", max_length=64),
    domain: str = Query("", max_length=64),
    include_deleted: bool = False,
    _user: Dict[str, str] = Depends(get_current_admin),
):
    return await _forward_knowledge_request(
        "/documents",
        method="GET",
        params={
            "page": page,
            "page_size": page_size,
            "search": search,
            "status": status,
            "knowledge_space": knowledge_space,
            "domain": domain,
            "include_deleted": str(include_deleted).lower(),
        },
    )


@router.get("/api/knowledge/documents/statistics", summary="Admin knowledge statistics")
async def knowledge_document_statistics(
    _user: Dict[str, str] = Depends(get_current_admin),
):
    return await _forward_knowledge_request("/documents/statistics", method="GET")


@router.delete("/api/knowledge/documents/{document_hash}", summary="Delete knowledge document")
async def delete_knowledge_document(
    document_hash: str,
    user: Dict[str, str] = Depends(get_current_admin),
):
    if len(document_hash) != 64 or any(
        char not in "0123456789abcdef" for char in document_hash.lower()
    ):
        raise HTTPException(status_code=400, detail="无效的文档 ID")
    return await _forward_knowledge_request(
        f"/documents/{document_hash}",
        method="DELETE",
        headers={"X-Actor-Id": user["username"]},
    )


@router.get("/api/knowledge/tasks/{task_id}", summary="Get knowledge ingestion task")
async def get_knowledge_task(task_id: str, _user: Dict[str, str] = Depends(get_current_admin)):
    return await _forward_knowledge_request(f"/tasks/{task_id}", method="GET")


@router.get("/api/knowledge/tasks", summary="List knowledge ingestion tasks")
async def list_knowledge_tasks(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    _user: Dict[str, str] = Depends(get_current_admin),
):
    return await _forward_knowledge_request("/tasks", method="GET", params={"page": page, "page_size": page_size})


@router.post("/api/knowledge/tasks/{task_id}/retry", summary="Retry knowledge ingestion task")
async def retry_knowledge_task(task_id: str, _user: Dict[str, str] = Depends(get_current_admin)):
    return await _forward_knowledge_request(f"/tasks/{task_id}/retry", method="POST")


async def _forward_knowledge_request(path: str, method: str = "POST", **kwargs):
    if not settings.KNOWLEDGE_BASE_URL:
        raise HTTPException(status_code=503, detail="知识库服务未配置")
    if not settings.KNOWLEDGE_SERVICE_TOKEN or len(settings.KNOWLEDGE_SERVICE_TOKEN) < 32:
        raise HTTPException(status_code=503, detail="知识库服务认证未配置")
    headers = dict(kwargs.pop("headers", {}))
    headers["X-Service-Token"] = settings.KNOWLEDGE_SERVICE_TOKEN
    try:
        async with httpx.AsyncClient(timeout=settings.KNOWLEDGE_REQUEST_TIMEOUT) as client:
            response = await client.request(
                method,
                settings.KNOWLEDGE_BASE_URL.rstrip("/") + path,
                headers=headers,
                **kwargs,
            )
        try:
            content = response.json()
        except ValueError:
            content = {"detail": "知识库服务返回了无效响应"}
        return JSONResponse(status_code=response.status_code, content=content)
    except httpx.HTTPError as error:
        logger.error("知识库服务请求失败: %s", error)
        raise HTTPException(status_code=502, detail="知识库服务暂时不可用") from error
